"""Replay a repo's declared history into a local git repository.

Used by ``seed.py`` (build, then push) and by ``validate`` (build, then prove
every scenario PR applies to the tree it will meet on GitHub). Nothing here
talks to GitHub.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from model import Commit, Edit, ReplayError, RepoSpec, ScenarioPR, apply_ops
from people import TEAM_SLUGS, person


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _identity_env(login: str, when: datetime) -> dict[str, str]:
    who = person(login)
    stamp = when.isoformat()
    return {
        "GIT_AUTHOR_NAME": who.name,
        "GIT_AUTHOR_EMAIL": who.email,
        "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_NAME": who.name,
        "GIT_COMMITTER_EMAIL": who.email,
        "GIT_COMMITTER_DATE": stamp,
    }


def check_author_window(repo: str, commit: Commit) -> None:
    who = person(commit.author)
    day = commit.when[:10]
    if day < who.joined:
        raise ReplayError(f"{repo}: {commit.author} commits on {day}, joined {who.joined}")
    if who.left and day > who.left:
        raise ReplayError(f"{repo}: {commit.author} commits on {day}, left {who.left}")


def build(spec: RepoSpec, workdir: Path) -> Path:
    """Create ``workdir/<repo>`` with the full backdated history on ``main``."""
    root = workdir / spec.name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    for i, commit in enumerate(spec.history):
        where = f"{spec.name} commit #{i} ({commit.when} {commit.message.splitlines()[0]!r})"
        check_author_window(spec.name, commit)
        apply_ops(root, commit.ops, where)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "--allow-empty-message", "-m", commit.message,
             env=_identity_env(commit.author, commit.timestamp()))
    return root


# ---------------------------------------------------------------------------
# Applied-state detection, shared with the live scenario engine
# ---------------------------------------------------------------------------


def pr_state(pr: ScenarioPR, read) -> str:
    """'applied', 'pending' or 'conflict' - judged from file contents.

    ``read(path)`` returns the file's text on the branch being checked, or
    ``None`` if it does not exist. Every op of a decoy/culprit is an Edit, so
    "applied" means every ``new`` is present and every ``old`` is gone.
    """
    applied = pending = 0
    for op in pr.ops:
        assert isinstance(op, Edit)
        text = read(op.path)
        if text is None:
            return "conflict"
        new_count = text.count(op.new)
        # An insert-style edit keeps its anchor: ``old`` occurs inside ``new``.
        # Occurrences of ``old`` that sit inside an applied ``new`` don't count.
        stray_old = text.count(op.old) - op.new.count(op.old) * new_count
        if new_count >= 1 and stray_old == 0:
            applied += 1
        elif new_count == 0 and text.count(op.old) == 1:
            pending += 1
        else:
            return "conflict"
    if applied == len(pr.ops):
        return "applied"
    if pending == len(pr.ops):
        return "pending"
    return "conflict"


def inverse(pr: ScenarioPR) -> tuple[Edit, ...]:
    return tuple(Edit(op.path, op.new, op.old) for op in pr.ops)  # type: ignore[union-attr]


def validate(spec: RepoSpec, workdir: Path) -> list[str]:
    """Build the history and walk every scenario PR through its lifecycle.

    Order mirrors a demo day: decoys (warmup), then for each culprit -
    apply, revert, apply again - proving induce/reset can cycle forever.
    """
    notes: list[str] = []
    if spec.team not in TEAM_SLUGS:
        raise ReplayError(f"{spec.name}: unknown owner team {spec.team!r}")
    for team, _perm in spec.team_access:
        if team not in TEAM_SLUGS:
            raise ReplayError(f"{spec.name}: unknown team {team!r} in team_access")

    root = build(spec, workdir)
    notes.append(f"{len(spec.history)} commits, head {_git(root, 'rev-parse', '--short', 'HEAD').strip()}")

    def read(path: str):
        p = root / path
        return p.read_text() if p.exists() else None

    for pr in spec.prs:
        person(pr.author)
        if pr.revert_author:
            person(pr.revert_author)
        unknown = set(pr.labels) - {label.name for label in spec.labels}
        if unknown:
            raise ReplayError(f"{spec.name}/{pr.key}: labels not declared on the repo: {sorted(unknown)}")

    opens = [p for p in spec.prs if p.kind == "open"]
    decoys = [p for p in spec.prs if p.kind == "decoy"]
    culprits = [p for p in spec.prs if p.kind == "culprit"]

    # Open PRs branch off the seeded head and are never merged.
    for pr in opens:
        scratch = workdir / f"{spec.name}--{pr.key}"
        shutil.copytree(root, scratch, dirs_exist_ok=False)
        apply_ops(scratch, pr.ops, f"{spec.name}/{pr.key}")
        shutil.rmtree(scratch)
        notes.append(f"open   {pr.key}: ok")

    for pr in decoys:
        state = pr_state(pr, read)
        if state != "pending":
            raise ReplayError(f"{spec.name}/{pr.key}: decoy is {state} on the seeded head")
        apply_ops(root, pr.ops, f"{spec.name}/{pr.key}")
        assert pr_state(pr, read) == "applied"
        notes.append(f"decoy  {pr.key}: ok")

    for pr in culprits:
        for cycle in (1, 2):
            if pr_state(pr, read) != "pending":
                raise ReplayError(f"{spec.name}/{pr.key}: culprit not pending before cycle {cycle}")
            apply_ops(root, pr.ops, f"{spec.name}/{pr.key}")
            if pr_state(pr, read) != "applied":
                raise ReplayError(f"{spec.name}/{pr.key}: culprit not applied after merge")
            apply_ops(root, inverse(pr), f"{spec.name}/{pr.key} revert")
        notes.append(f"culprit {pr.key}: apply/revert x2 ok")
    return notes
