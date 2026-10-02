#!/usr/bin/env python3
"""Open and merge the pull requests that make the demo incidents real.

GitHub stamps pull requests with wall-clock time, so the PRs that must sit
close to an incident are created live rather than seeded:

    scenario.py warmup [--scenario S]   merge the day's decoy PRs (run 30+ min before the show)
    scenario.py culprit S                merge S's culprit PR (the induce scripts call this)
    scenario.py revert S                 merge a revert of S's culprit (the reset scripts call this)
    scenario.py open-prs                 make sure every 'open' PR exists (seed.py push calls this)
    scenario.py status                   state of every scenario PR on main
    scenario.py fetch REPO PATH          print a file from main
    scenario.py enabled                  exit 0 if the GitHub side of the scenarios is switched on

S is a scenario from ``model.SCENARIOS`` - today only ``consumer-lag``.

State comes from the files on ``main``, never from a local record: a PR is
"applied" when every one of its edits is present. That makes every command
idempotent and safe to repeat - ``culprit`` twice merges one PR, ``revert``
on a green repo does nothing - which is what stage machinery needs.

Each PR is a single commit authored and committed by the persona (backdated
a few minutes, the way a branch is pushed before its PR is opened). It lands
by fast-forwarding main to that commit, so the history on main is the
persona's alone; GitHub then marks the PR merged. GitHub records the PR
itself as opened and merged by the token's account - no API can change that.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import load_repos  # noqa: E402
from gh import GitHub, GitHubError, resolve_token  # noqa: E402
from model import (  # noqa: E402
    ORG,
    SCENARIOS,
    Delete,
    Edit,
    RepoSpec,
    ScenarioPR,
    Write,
    apply_edit,
)
from people import person  # noqa: E402
from replay import inverse, pr_state  # noqa: E402


def log(msg: str) -> None:
    print(f"[github] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Enablement
# ---------------------------------------------------------------------------


def github_scenarios_enabled() -> bool:
    """``GITHUB_SCENARIO`` = on | off | auto (default).

    auto turns the GitHub side on when the agent is pointed at real GitHub
    (``GITHUB_MODE=live``) and a write token is available - the only setup in
    which merging a culprit PR is visible to the agent at all.
    """
    raw = os.environ.get("GITHUB_SCENARIO", "auto").strip().lower()
    if raw in ("0", "off", "false", "no"):
        return False
    if raw in ("1", "on", "true", "yes"):
        return True
    mode = os.environ.get("GITHUB_MODE", "stub").strip().lower()
    return mode in ("live", "real") and resolve_token(required=False) is not None


# ---------------------------------------------------------------------------
# Repo helpers
# ---------------------------------------------------------------------------


class Repo:
    def __init__(self, gh: GitHub, spec: RepoSpec):
        self.gh, self.spec, self.name = gh, spec, spec.name
        self.base = f"/repos/{ORG}/{spec.name}"
        self._cache: dict[str, str | None] = {}

    def read(self, path: str) -> str | None:
        if path not in self._cache:
            self._cache[path] = self.gh.read_file(ORG, self.name, path)
        return self._cache[path]

    def state(self, pr: ScenarioPR) -> str:
        self._cache.clear()
        return pr_state(pr, self.read)

    def head(self) -> tuple[str, str]:
        ref = self.gh.get(f"{self.base}/git/ref/heads/main")
        sha = ref["object"]["sha"]
        tree = self.gh.get(f"{self.base}/git/commits/{sha}")["tree"]["sha"]
        return sha, tree

    def commit(self, ops, message: str, author_login: str, when: datetime, parent: str, base_tree: str) -> str:
        """Create one commit on top of ``parent`` without touching any branch."""
        self._cache.clear()
        entries = []
        for op in ops:
            if isinstance(op, Edit):
                current = self.read(op.path)
                if current is None:
                    raise RuntimeError(f"{self.name}: {op.path} does not exist on main")
                entries.append({"path": op.path, "mode": "100644", "type": "blob",
                                "content": apply_edit(current, op, f"{self.name}:{op.path}")})
            elif isinstance(op, Write):
                entries.append({"path": op.path, "mode": "100755" if op.executable else "100644",
                                "type": "blob", "content": op.text()})
            elif isinstance(op, Delete):
                entries.append({"path": op.path, "mode": "100644", "type": "blob", "sha": None})
        tree = self.gh.post(f"{self.base}/git/trees", {"base_tree": base_tree, "tree": entries})
        who = person(author_login)
        ident = {"name": who.name, "email": who.email,
                 "date": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        commit = self.gh.post(f"{self.base}/git/commits", {
            "message": message, "tree": tree["sha"], "parents": [parent],
            "author": ident, "committer": ident,
        })
        return commit["sha"]

    def push_branch(self, branch: str, sha: str) -> None:
        status, _ = self.gh.request("POST", f"{self.base}/git/refs",
                                    {"ref": f"refs/heads/{branch}", "sha": sha}, allow=(422,))
        if status == 422:  # left over from an earlier run - point it at the new commit
            self.gh.patch(f"{self.base}/git/refs/heads/{branch}", {"sha": sha, "force": True})

    def open_pr(self, branch: str, title: str, body: str, labels: tuple[str, ...]) -> dict:
        pr = self.gh.post(f"{self.base}/pulls", {
            "title": title, "head": branch, "base": "main", "body": body,
            "maintainer_can_modify": True,
        })
        if labels:
            self.gh.post(f"{self.base}/issues/{pr['number']}/labels", {"labels": list(labels)})
        return pr

    def merge(self, number: int, head_sha: str) -> dict:
        """Land the PR's commit on main with the persona still its committer.

        Fast-forwarding main to the PR head keeps the commit byte-identical -
        author AND committer stay the persona - and GitHub then marks the PR
        merged on its own. The merge API cannot do that: every method rewrites
        the commit or adds one, committed by the token's account, which would
        put the operator's name into the bank's history. If main moved since
        the branch was cut, fall back to a rebase merge.
        """
        status, _ = self.gh.request("PATCH", f"{self.base}/git/refs/heads/main",
                                    {"sha": head_sha, "force": False}, allow=(422,))
        if status == 200:
            for attempt in range(15):
                pr = self.gh.get(f"{self.base}/pulls/{number}")
                if pr.get("merged_at"):
                    return {"sha": head_sha}
                time.sleep(1 + attempt * 0.5)
            log(f"{self.name}#{number}: main fast-forwarded but GitHub has not marked the PR merged yet")
            return {"sha": head_sha}
        # Mergeability is computed asynchronously right after the PR opens;
        # GitHub answers 405 until it is known.
        for attempt in range(10):
            status, body = self.gh.request(
                "PUT", f"{self.base}/pulls/{number}/merge",
                {"merge_method": "rebase"}, allow=(405, 409),
            )
            if status == 200:
                return body
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"{self.name}#{number}: not mergeable: {body}")

    def find_merged(self, branch: str) -> dict | None:
        pulls = self.gh.get(f"{self.base}/pulls", params={
            "state": "closed", "head": f"{ORG}:{branch}", "sort": "updated",
            "direction": "desc", "per_page": 10,
        })
        merged = [p for p in pulls if p.get("merged_at")]
        return max(merged, key=lambda p: p["merged_at"]) if merged else None

    def find_open(self, branch: str) -> dict | None:
        pulls = self.gh.get(f"{self.base}/pulls", params={
            "state": "open", "head": f"{ORG}:{branch}", "per_page": 5,
        })
        return pulls[0] if pulls else None


def _authored_at(minutes_ago: tuple[int, int]) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=random.randint(*minutes_ago))


def create_and_merge(repo: Repo, pr: ScenarioPR, *, ops=None, title=None, body=None,
                     author=None, branch=None, message=None, labels=None,
                     minutes_ago=(12, 35)) -> dict:
    parent, base_tree = repo.head()
    sha = repo.commit(ops or pr.ops, message or pr.commit_message, author or pr.author,
                      _authored_at(minutes_ago), parent, base_tree)
    branch = branch or pr.branch
    repo.push_branch(branch, sha)
    opened = repo.open_pr(branch, title or pr.title, body if body is not None else pr.body,
                          labels if labels is not None else pr.labels)
    merged = repo.merge(opened["number"], sha)
    # Re-read for merged_at/merge_commit_sha (the merge response only has the sha).
    final = repo.gh.get(f"{repo.base}/pulls/{opened['number']}")
    return {
        "repo": f"{ORG}/{repo.name}", "number": final["number"], "title": final["title"],
        "url": final["html_url"], "merged_at": final["merged_at"],
        "merge_commit_sha": merged.get("sha") or final.get("merge_commit_sha"),
        "commit_author": person(author or pr.author).name,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _index(specs: list[RepoSpec]) -> list[tuple[RepoSpec, ScenarioPR]]:
    return [(s, p) for s in specs for p in s.prs]


def warm(gh: GitHub, specs, scenario: str | None, *, late: bool = False) -> list[dict]:
    done = []
    for spec, pr in _index(specs):
        if pr.kind != "decoy" or (scenario and pr.scenario not in (scenario, None)):
            continue
        repo = Repo(gh, spec)
        state = repo.state(pr)
        if state == "applied":
            log(f"decoy {pr.key}: already on main")
            continue
        if state == "conflict":
            log(f"decoy {pr.key}: WARNING - main has diverged from what the PR edits; skipped")
            continue
        info = create_and_merge(repo, pr, minutes_ago=(3, 9) if late else (25, 80))
        log(f"decoy {pr.key}: merged {info['repo']}#{info['number']} ({info['title']})")
        done.append(info)
    if late and done:
        log("NOTE: decoys were merged seconds before the culprit. For a natural timeline, "
            "run `make gh-warmup` at least 30 minutes before the demo.")
    return done


def culprit(gh: GitHub, specs, scenario: str) -> dict | None:
    warm(gh, specs, scenario, late=True)
    for spec, pr in _index(specs):
        if pr.kind == "culprit" and pr.scenario == scenario:
            repo = Repo(gh, spec)
            state = repo.state(pr)
            if state == "applied":
                existing = repo.find_merged(pr.branch)
                log(f"culprit {pr.key}: already on main"
                    + (f" ({existing['html_url']})" if existing else ""))
                return {"repo": f"{ORG}/{spec.name}", "already_applied": True,
                        "url": existing and existing["html_url"]}
            if state == "conflict":
                raise RuntimeError(f"{pr.key}: main has diverged from the culprit's edits")
            info = create_and_merge(repo, pr)
            log(f"culprit {pr.key}: merged {info['url']} by {info['commit_author']}")
            return info
    raise KeyError(f"no culprit declared for scenario {scenario!r}")


def revert(gh: GitHub, specs, scenario: str) -> dict | None:
    for spec, pr in _index(specs):
        if pr.kind == "culprit" and pr.scenario == scenario:
            repo = Repo(gh, spec)
            state = repo.state(pr)
            if state != "applied":
                log(f"revert {pr.key}: culprit not on main ({state}); nothing to revert")
                return None
            original = repo.find_merged(pr.branch)
            number = original["number"] if original else None
            title = f'Revert "{pr.title}"'
            body = (f"Reverts {ORG}/{spec.name}#{number}\n\n" if number else "") + pr.revert_body
            message = (f'Revert "{pr.commit_message.splitlines()[0]}"\n\n'
                       f"This reverts commit {original['merge_commit_sha'] if original else ''}.").strip()
            info = create_and_merge(
                repo, pr, ops=inverse(pr), title=title, body=body,
                author=pr.revert_author or pr.author, message=message, labels=(),
                branch=f"revert-{number or 'x'}-{pr.branch}", minutes_ago=(2, 6),
            )
            log(f"revert {pr.key}: merged {info['url']}")
            return info
    raise KeyError(f"no culprit declared for scenario {scenario!r}")


def ensure_open_prs(gh: GitHub, specs) -> list[dict]:
    out = []
    for spec, pr in _index(specs):
        if pr.kind != "open":
            continue
        repo = Repo(gh, spec)
        existing = repo.find_open(pr.branch)
        if existing:
            log(f"open {pr.key}: exists ({existing['html_url']})")
            continue
        parent, base_tree = repo.head()
        sha = repo.commit(pr.ops, pr.commit_message, pr.author,
                          _authored_at((60 * 24 * 5, 60 * 24 * 9)), parent, base_tree)
        repo.push_branch(pr.branch, sha)
        opened = repo.open_pr(pr.branch, pr.title, pr.body, pr.labels)
        log(f"open {pr.key}: opened {opened['html_url']}")
        out.append({"repo": f"{ORG}/{spec.name}", "number": opened["number"], "url": opened["html_url"]})
    return out


def culprit_states(gh: GitHub, specs) -> list[dict]:
    """Where each scenario's culprit stands on main: applied, pending or conflict."""
    return [
        {"scenario": pr.scenario, "repo": f"{ORG}/{spec.name}", "title": pr.title,
         "state": Repo(gh, spec).state(pr)}
        for spec, pr in _index(specs)
        if pr.kind == "culprit"
    ]


def status(gh: GitHub, specs) -> int:
    for spec, pr in _index(specs):
        repo = Repo(gh, spec)
        try:
            if pr.kind == "open":
                st = "open" if repo.find_open(pr.branch) else "missing"
            else:
                st = repo.state(pr)
        except GitHubError as exc:
            st = f"error {exc.status}"
        print(f"{spec.name:28} {pr.kind:8} {pr.scenario or '-':18} {st:9} {pr.title}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("warmup").add_argument("--scenario", choices=SCENARIOS)
    sub.add_parser("culprit").add_argument("scenario", choices=SCENARIOS)
    sub.add_parser("revert").add_argument("scenario", choices=SCENARIOS)
    sub.add_parser("open-prs")
    sub.add_parser("status")
    p = sub.add_parser("fetch")
    p.add_argument("repo")
    p.add_argument("path")
    sub.add_parser("enabled")
    args = ap.parse_args(argv)

    if args.cmd == "enabled":
        return 0 if github_scenarios_enabled() else 1

    gh = GitHub()
    if args.cmd == "fetch":
        text = gh.read_file(ORG, args.repo, args.path)
        if text is None:
            log(f"{ORG}/{args.repo}:{args.path} not found on main")
            return 1
        sys.stdout.write(text)
        return 0

    specs = load_repos()
    if args.cmd == "warmup":
        print(json.dumps(warm(gh, specs, args.scenario), indent=2))
    elif args.cmd == "culprit":
        print(json.dumps(culprit(gh, specs, args.scenario), indent=2))
    elif args.cmd == "revert":
        print(json.dumps(revert(gh, specs, args.scenario), indent=2))
    elif args.cmd == "open-prs":
        print(json.dumps(ensure_open_prs(gh, specs), indent=2))
    elif args.cmd == "status":
        return status(gh, specs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
