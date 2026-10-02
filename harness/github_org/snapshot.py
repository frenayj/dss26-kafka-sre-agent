#!/usr/bin/env python3
"""Freeze the DSS26 Bank GitHub org into one JSON file for the offline stub.

The GitHub MCP stub (``harness/stubs/github_mcp.py``) serves the official
server's tool names from this snapshot, so ``GITHUB_MODE=stub`` tells the same
story as the live org: same repos, files, history, PRs and diffs.

The snapshot is the org on the afternoon of the demo: every decoy merged in
the morning, each culprit merged minutes before its incident, open PRs
open. PR and scenario-commit times are stored as offsets from "now" and
materialised when the stub serves them, the same trick ``harness.scenarios.freshen``
plays on the PagerDuty incidents, so a stub run always looks like it is
happening today. Historical commits keep their real (backdated) dates.

Built offline from the declarations in ``repos/`` - no GitHub access:

    python3 harness/github_org/snapshot.py   # -> harness/stubs/data/github-dss26-org.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import load_repos  # noqa: E402
from model import ORG, REPO_ROOT, RepoSpec, apply_ops  # noqa: E402
from people import person  # noqa: E402
from replay import build  # noqa: E402

OUT = REPO_ROOT / "harness" / "stubs" / "data" / f"github-{ORG}.json"

# Minutes before "now" each scenario PR was merged in the frozen afternoon.
# Decoys spread over the morning; culprits land ~11-12 minutes before the
# incident they cause (the stub freshens incidents to "now" as well).
def decoy_clock(n: int) -> list[int]:
    """Merge times for n decoys, spread from ~5h to ~45min before now."""
    if n <= 1:
        return [120] * n
    return [round(300 - i * (255 / (n - 1))) for i in range(n)]
CULPRIT_MERGE_MINUTES = {"consumer-lag": 11}
OPEN_PR_CREATED_MINUTES = 6 * 24 * 60 + 130

# Checks the CI of each Tier-A repo runs on a pull request, as GitHub reports
# them: (check name, conclusion). The shared schema-compat job has been
# disabled since 2026-04-15, which GitHub shows as "skipped".
CHECKS = {
    "merchant-gateway": (("build", "success"), ("schema-compat / compat", "skipped")),
    "fraud-decisioning-svc": (("test", "success"), ("schema-compat / compat", "skipped")),
    "kafka-platform": (("validate", "success"),),
}

TEXT_SUFFIXES = {
    ".md", ".yaml", ".yml", ".json", ".avsc", ".properties", ".py", ".java", ".kt",
    ".kts", ".xml", ".tf", ".go", ".ts", ".tsx", ".js", ".sql", ".sh", ".txt", ".toml",
    ".cfg", ".ini", ".gradle", ".scala", ".sbt", ".mod", ".sum", ".conf", ".hcl",
    ".dockerignore", ".gitignore", ".env", ".html", ".css", ".proto", ".lock",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def _identity(login: str) -> dict:
    who = person(login)
    return {"name": who.name, "email": who.email}


def _commit_files(root: Path, sha: str) -> list[dict]:
    files = []
    numstat = _git(root, "show", "--format=", "--numstat", "--no-renames", sha)
    status = dict(
        reversed(line.split("\t", 1))
        for line in _git(root, "show", "--format=", "--name-status", "--no-renames", sha).splitlines()
        if line.strip()
    )
    for line in numstat.splitlines():
        if not line.strip():
            continue
        add, delete, path = line.split("\t", 2)
        patch = _git(root, "show", "--format=", "--no-renames", sha, "--", path)
        # Keep only the hunks, like the API's per-file ``patch`` field.
        hunk_start = patch.find("\n@@")
        files.append({
            "filename": path,
            "status": {"A": "added", "D": "removed"}.get(status.get(path, "M"), "modified"),
            "additions": int(add) if add.isdigit() else 0,
            "deletions": int(delete) if delete.isdigit() else 0,
            "patch": patch[hunk_start + 1:] if hunk_start >= 0 else "",
        })
    return files


def _commits(root: Path, rev_range: str) -> list[dict]:
    fmt = "%H%x1f%an%x1f%ae%x1f%aI%x1f%cn%x1f%ce%x1f%cI%x1f%B%x1e"
    out = []
    for rec in _git(root, "log", f"--format={fmt}", rev_range).split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, an, ae, ad, cn, ce, cd, msg = rec.split("\x1f")
        out.append({
            "sha": sha, "message": msg.strip(),
            "author": {"name": an, "email": ae, "date": ad},
            "committer": {"name": cn, "email": ce, "date": cd},
            "files": _commit_files(root, sha),
        })
    return out


def _tree(root: Path) -> dict[str, dict]:
    files = {}
    for line in _git(root, "ls-tree", "-r", "HEAD").splitlines():
        meta, path = line.split("\t", 1)
        _mode, _type, sha = meta.split()
        p = root / path
        if p.suffix.lower() not in TEXT_SUFFIXES and p.name not in (
            "Dockerfile", "Makefile", "CODEOWNERS", "LICENSE", "mvnw", ".gitignore",
        ):
            continue
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue
        files[path] = {"sha": sha, "size": len(text.encode()), "text": text}
    return files


def _commit_scenario(root: Path, spec: RepoSpec, pr) -> str:
    apply_ops(root, pr.ops, f"{spec.name}/{pr.key}")
    _git(root, "add", "-A")
    who = _identity(pr.author)
    env = {"GIT_AUTHOR_NAME": who["name"], "GIT_AUTHOR_EMAIL": who["email"],
           "GIT_COMMITTER_NAME": "GitHub", "GIT_COMMITTER_EMAIL": "noreply@github.com",
           # Placeholder date; the stub rewrites scenario commits relative to now.
           "GIT_AUTHOR_DATE": "2026-10-01T12:00:00Z", "GIT_COMMITTER_DATE": "2026-10-01T12:00:00Z"}
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", pr.commit_message],
                   cwd=root, env={**os.environ, **env}, check=True)
    return _git(root, "rev-parse", "HEAD").strip()


def snapshot_repo(spec: RepoSpec, workdir: Path, decoy_clock: list[int]) -> dict:
    root = build(spec, workdir)
    seeded_head = _git(root, "rev-parse", "HEAD").strip()
    history = _commits(root, "HEAD")
    for c in history:
        c["relative_minutes"] = None

    prs, number = [], 0
    scenario_commits = []

    # Open PRs come first: they were opened at seed time, before the demo day.
    for pr in (p for p in spec.prs if p.kind == "open"):
        number += 1
        branch_root = workdir / f"{spec.name}--{pr.key}"
        subprocess.run(["cp", "-R", str(root), str(branch_root)], check=True)
        sha = _commit_scenario(branch_root, spec, pr)
        commit = _commits(branch_root, f"{seeded_head}..{sha}")[0]
        commit["relative_minutes"] = OPEN_PR_CREATED_MINUTES + 25
        commit["committer"] = dict(commit["author"])
        prs.append(_pr_record(spec, pr, number, commit, branch_root, seeded_head, sha,
                              state="open", created=OPEN_PR_CREATED_MINUTES, merged=None))

    ordered = [p for p in spec.prs if p.kind == "decoy"] + [p for p in spec.prs if p.kind == "culprit"]
    for pr in ordered:
        number += 1
        parent = _git(root, "rev-parse", "HEAD").strip()
        merged = decoy_clock.pop(0) if pr.kind == "decoy" else CULPRIT_MERGE_MINUTES[pr.scenario]
        sha = _commit_scenario(root, spec, pr)
        commit = _commits(root, f"{parent}..{sha}")[0]
        commit["relative_minutes"] = merged + 1   # authored a little before the merge
        scenario_commits.append(commit)
        prs.append(_pr_record(spec, pr, number, commit, root, parent, sha,
                              state="closed", created=merged + 18, merged=merged))

    # Main's commit list, newest first. Scenario commits go on top in merge order.
    scenario_commits.sort(key=lambda c: c["relative_minutes"])
    return {
        "name": spec.name,
        "full_name": f"{ORG}/{spec.name}",
        "description": spec.description,
        "topics": list(spec.topics),
        "team": spec.team,
        "language": _language(root),
        "created_at": spec.history[0].timestamp().isoformat(),
        "files": _tree(root),
        "commits": scenario_commits + history,
        "pulls": prs,
    }


def _pr_record(spec, pr, number, commit, root, base_sha, head_sha, *, state, created, merged):
    diff = _git(root, "diff", "--no-renames", base_sha, head_sha)
    return {
        "number": number,
        "key": pr.key,
        "title": pr.title,
        "body": pr.body,
        "state": state,
        "draft": False,
        "labels": list(pr.labels),
        "user": pr.author.replace(".", "-"),
        "head_ref": pr.branch,
        "base_ref": "main",
        "head_sha": head_sha,
        "base_sha": base_sha,
        "created_minutes": created,
        "merged_minutes": merged,
        "commits": [commit],
        "files": commit["files"],
        "diff": diff,
        "head_files": {f["filename"]: (root / f["filename"]).read_text()
                       for f in commit["files"] if (root / f["filename"]).exists()},
        "checks": [list(c) for c in CHECKS.get(spec.name, ())],
    }


def _language(root: Path) -> str | None:
    counts: dict[str, int] = {}
    ext_lang = {".java": "Java", ".kt": "Kotlin", ".py": "Python", ".go": "Go", ".ts": "TypeScript",
                ".tsx": "TypeScript", ".tf": "HCL", ".scala": "Scala", ".properties": None}
    for p in root.rglob("*"):
        lang = ext_lang.get(p.suffix)
        if lang and ".git" not in p.parts:
            counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=counts.get) if counts else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    specs = load_repos()
    clock = decoy_clock(sum(1 for s in specs for p in s.prs if p.kind == "decoy"))
    with tempfile.TemporaryDirectory(prefix="dss26-snapshot-") as tmp:
        repos = [snapshot_repo(s, Path(tmp), clock) for s in specs]
    data = {"org": ORG, "generated_from": "harness/github_org (repos/ declarations)",
            "repos": repos}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, sort_keys=False) + "\n")
    n_prs = sum(len(r["pulls"]) for r in repos)
    print(f"wrote {out} - {len(repos)} repos, {n_prs} PRs, "
          f"{out.stat().st_size // 1024} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
