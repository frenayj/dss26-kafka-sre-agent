"""GitHub commands for seed.py: teams, push, status.

Kept apart from seed.py so the offline commands (validate, build) work on a
machine with no token at all.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from catalog import load_repos
from gh import GitHub, GitHubError
from model import ORG, RepoSpec
from people import TEAMS
from replay import build


def log(msg: str) -> None:
    print(f"[seed] {msg}", flush=True)


SCOPE_HINT = (
    "Your token lacks a scope this step needs. With the gh CLI run:\n"
    "    gh auth refresh -h github.com -s admin:org,delete_repo\n"
    "(admin:org creates teams and grants them repos; delete_repo is only for --rebuild)."
)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


def ensure_teams(gh: GitHub) -> dict[str, int]:
    ids: dict[str, int] = {}
    for team in TEAMS:  # parents are declared before their children
        status, existing = gh.request("GET", f"/orgs/{ORG}/teams/{team.slug}", allow=(404,))
        payload = {"name": team.name, "description": team.description, "privacy": "closed"}
        if team.parent:
            payload["parent_team_id"] = ids[team.parent]
        try:
            if status == 404:
                created = gh.post(f"/orgs/{ORG}/teams", payload)
                ids[team.slug] = created["id"]
                log(f"team {team.slug}: created")
            else:
                gh.patch(f"/orgs/{ORG}/teams/{team.slug}", payload)
                ids[team.slug] = existing["id"]
                log(f"team {team.slug}: up to date")
        except GitHubError as exc:
            if exc.status in (403, 404):
                sys.exit(f"[seed] cannot manage teams ({exc.status}).\n{SCOPE_HINT}")
            raise
    return ids


# ---------------------------------------------------------------------------
# Repos
# ---------------------------------------------------------------------------


REPO_SETTINGS = {
    "private": True,
    "has_issues": True,
    "has_projects": False,
    "has_wiki": False,
    "allow_squash_merge": True,
    "allow_merge_commit": True,
    "allow_rebase_merge": True,
    "delete_branch_on_merge": True,
}


def _is_empty(gh: GitHub, name: str) -> bool:
    status, _ = gh.request("GET", f"/repos/{ORG}/{name}/commits", params={"per_page": 1},
                           allow=(409,))
    return status == 409  # "Git Repository is empty."


def _push_history(gh: GitHub, spec: RepoSpec) -> None:
    with tempfile.TemporaryDirectory(prefix="dss26-seed-") as tmp:
        root = build(spec, Path(tmp))
        url = f"https://github.com/{ORG}/{spec.name}.git"
        proc = subprocess.run(
            ["git", "-c", f"http.extraHeader={gh.basic_auth_header()}",
             "push", "--quiet", url, "main:main"],
            cwd=root, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            # Never echo the command line: it carries the token.
            raise RuntimeError(f"git push to {ORG}/{spec.name} failed: {proc.stderr.strip()}")


def _apply_settings(gh: GitHub, spec: RepoSpec) -> None:
    base = f"/repos/{ORG}/{spec.name}"
    gh.patch(base, {"description": spec.description, **REPO_SETTINGS})
    gh.put(f"{base}/topics", {"names": list(spec.topics)})

    existing = {lb["name"]: lb for lb in gh.get(f"{base}/labels", params={"per_page": 100})}
    for label in spec.labels:
        body = {"name": label.name, "color": label.color, "description": label.description}
        if label.name in existing:
            gh.patch(f"{base}/labels/{label.name}", body)
        else:
            gh.post(f"{base}/labels", body)

    grants = ((spec.team, "maintain"),) + spec.team_access
    for team, permission in grants:
        try:
            gh.put(f"/orgs/{ORG}/teams/{team}/repos/{ORG}/{spec.name}", {"permission": permission})
        except GitHubError as exc:
            if exc.status in (403, 404):
                log(f"{spec.name}: could not grant {team} ({exc.status}) - run `seed.py teams` first")
            else:
                raise

    if spec.actions_access_org:
        gh.put(f"{base}/actions/permissions/access", {"access_level": "organization"})


def push(gh: GitHub, specs: list[RepoSpec], rebuild: bool) -> None:
    # Repos other repos' workflows call must exist (and be callable) before
    # those callers' first CI run, or that run fails with "workflow not found".
    specs = sorted(specs, key=lambda s: (not s.actions_access_org, s.tier, s.name))
    for spec in specs:
        path = f"/repos/{ORG}/{spec.name}"
        exists = gh.exists(path)
        if exists and rebuild:
            try:
                gh.delete(path)
            except GitHubError as exc:
                if exc.status == 403:
                    sys.exit(f"[seed] cannot delete {spec.name}.\n{SCOPE_HINT}")
                raise
            log(f"{spec.name}: deleted (rebuild)")
            exists = False
        if not exists:
            gh.post(f"/orgs/{ORG}/repos", {"name": spec.name, **REPO_SETTINGS,
                                           "description": spec.description})
            log(f"{spec.name}: created")
        if _is_empty(gh, spec.name):
            _push_history(gh, spec)
            log(f"{spec.name}: pushed {len(spec.history)} commits")
        else:
            log(f"{spec.name}: has history already - kept (use --rebuild to rewrite)")
        _apply_settings(gh, spec)

    from scenario import ensure_open_prs  # needs the repos to exist
    ensure_open_prs(gh, specs)


def status(gh: GitHub, specs: list[RepoSpec]) -> None:
    for spec in specs:
        path = f"/repos/{ORG}/{spec.name}"
        if not gh.exists(path):
            print(f"{spec.name:28} missing")
            continue
        empty = _is_empty(gh, spec.name)
        print(f"{spec.name:28} {'EMPTY' if empty else 'seeded'}  tier {spec.tier}  {spec.team}")
    print()
    from scenario import status as pr_status
    pr_status(gh, specs)


# ---------------------------------------------------------------------------
# CLI wiring (called from seed.py)
# ---------------------------------------------------------------------------


def register(sub) -> None:
    p = sub.add_parser("teams", help="create/update teams")
    p.set_defaults(fn=lambda a: (ensure_teams(GitHub()), 0)[1])

    p = sub.add_parser("push", help="create repos and push their history")
    p.add_argument("repos", nargs="*")
    p.add_argument("--rebuild", action="store_true",
                   help="DELETE and recreate the repos (drops every PR)")
    # Naming repos explicitly tolerates repo modules that are not written yet.
    p.set_defaults(fn=lambda a: (push(GitHub(), load_repos(only=tuple(a.repos) or None,
                                                           strict=not a.repos),
                                      a.rebuild), 0)[1])

    p = sub.add_parser("status", help="repos and scenario PR states")
    p.set_defaults(fn=lambda a: (status(GitHub(), load_repos()), 0)[1])
