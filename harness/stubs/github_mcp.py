"""GitHub MCP stub (stdio) - an offline stand-in for GitHub's official server.

Live mode (``GITHUB_MODE=live``) does not run this module: the agent talks to
github/github-mcp-server directly (see ``agent.mcp_clients``). This stub is
the ``stub`` back-end, and it is built to be indistinguishable to the model:

* **Same tool surface.** It serves the official server's tool definitions -
  names, descriptions and input schemas - verbatim from
  ``data/github_mcp_tools.json`` (captured from v1.12.2 with the same
  ``--read-only --tools`` allowlist live mode uses), so forensics' prompt and
  the UI renderers never branch on the mode.
* **Same org.** It serves ``data/github-dss26-org.json``, a snapshot built
  offline from the declarations in ``harness/github_org/`` - the very repos,
  files, backdated history and pull requests that ``seed.py`` pushes to the
  real ``dss26-org``. Regenerate it with ``harness/github_org/snapshot.py``.
* **Same shapes.** Results mirror the official server's JSON (search results,
  minimal PR/commit objects, two-part file contents).

The snapshot is the org on the afternoon of the demo: decoy PRs merged in the
morning, both culprit PRs merged minutes before their incident, open PRs
open. Their timestamps are stored relative to "now" and materialised per
call, like ``harness.scenarios.freshen`` does for the incidents.

Nothing here knows which PR is the culprit or answers a question the model
did not ask: search is real (qualifiers, terms, date ranges), and an unknown
repo or file is an error, exactly as on GitHub.

Run directly with:
    python -m harness.stubs.github_mcp
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent / "data"
TOOLS_FILE = DATA / "github_mcp_tools.json"

HTML = "https://github.com"
API = "https://api.github.com"


class NotFound(Exception):
    pass


def _num(*parts: Any, digits: int = 9) -> int:
    """Stable numeric id (``hash()`` is salted per process)."""
    return zlib.crc32("|".join(map(str, parts)).encode()) % 10 ** digits


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def _snapshot_path() -> Path:
    found = sorted(DATA.glob("github-*.json"))
    if not found:
        raise FileNotFoundError(
            f"no GitHub snapshot in {DATA} - run harness/github_org/snapshot.py"
        )
    return found[0]


class Org:
    """The frozen org, with relative timestamps resolved against ``now``."""

    def __init__(self, data: dict, now: Optional[datetime] = None):
        self.name: str = data["org"]
        self.now = now or datetime.now(timezone.utc)
        self.repos: dict[str, dict] = {r["name"]: r for r in data["repos"]}
        for repo in self.repos.values():
            for commit in repo["commits"]:
                self._freshen_commit(commit)
            for pr in repo["pulls"]:
                for commit in pr["commits"]:
                    self._freshen_commit(commit)

    def ago(self, minutes: Optional[float]) -> Optional[str]:
        if minutes is None:
            return None
        return _iso(self.now - timedelta(minutes=minutes))

    def _freshen_commit(self, commit: dict) -> None:
        minutes = commit.get("relative_minutes")
        if minutes is not None:
            commit["author"]["date"] = self.ago(minutes)
            commit["committer"]["date"] = self.ago(max(minutes - 1, 0))
        else:  # GitHub reports git dates in UTC
            for who in ("author", "committer"):
                commit[who]["date"] = _iso(_parse_when(commit[who]["date"]))

    def repo(self, owner: str, name: str) -> dict:
        if (owner or "").lower() != self.name.lower() or name not in self.repos:
            raise NotFound(f"failed to get repository {owner}/{name}: 404 Not Found")
        return self.repos[name]

    def pr(self, owner: str, name: str, number: int) -> tuple[dict, dict]:
        repo = self.repo(owner, name)
        for pr in repo["pulls"]:
            if pr["number"] == int(number):
                return repo, pr
        raise NotFound(f"failed to get pull request {owner}/{name}#{number}: 404 Not Found")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_when(value: str, end_of_day: bool = False) -> Optional[datetime]:
    value = value.strip()
    if not value or value == "*":
        return None
    try:
        if len(value) == 10:
            day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return day + timedelta(days=1) - timedelta(seconds=1) if end_of_day else day
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _date_filter(expr: str) -> Callable[[Optional[str]], bool]:
    """GitHub search date syntax: >=D, >D, <=D, <D, D, A..B, A..*, *..B."""
    if ".." in expr:
        lo, hi = expr.split("..", 1)
        lo_dt, hi_dt = _parse_when(lo), _parse_when(hi, end_of_day=True)
        return lambda v: v is not None and (lo_dt is None or _parse_when(v) >= lo_dt) and (
            hi_dt is None or _parse_when(v) <= hi_dt)
    for op in (">=", "<=", ">", "<"):
        if expr.startswith(op):
            ref = _parse_when(expr[len(op):], end_of_day=op in ("<=", ">"))
            cmp = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
                   ">": lambda a, b: a > b, "<": lambda a, b: a < b}[op]
            return lambda v: v is not None and ref is not None and cmp(_parse_when(v), ref)
    start, end = _parse_when(expr), _parse_when(expr, end_of_day=True)
    return lambda v: v is not None and start is not None and start <= _parse_when(v) <= end


def _tokens(query: str) -> list[str]:
    try:
        return shlex.split(query)
    except ValueError:
        return query.split()


def _paginate(items: list, page: Any, per_page: Any, default: int = 30) -> list:
    per = max(1, min(int(per_page or default), 100))
    start = (max(1, int(page or 1)) - 1) * per
    return items[start:start + per]


def _pick(obj: dict, fields: Optional[list]) -> dict:
    return {k: v for k, v in obj.items() if k in fields} if fields else obj


# ---------------------------------------------------------------------------
# Object builders (official server shapes)
# ---------------------------------------------------------------------------


def _user(login: str) -> dict:
    return {"login": login, "id": _num(login, digits=8),
            "profile_url": f"{HTML}/{login}",
            "avatar_url": f"https://avatars.githubusercontent.com/u/{_num(login, digits=8)}?v=4"}


def _search_user(login: str) -> dict:
    base = _user(login)
    return {"login": login, "id": base["id"], "avatar_url": base["avatar_url"],
            "html_url": base["profile_url"], "type": "User", "site_admin": False,
            "url": f"{API}/users/{login}"}


def _pr_times(org: Org, pr: dict) -> dict:
    created = org.ago(pr["created_minutes"])
    merged = org.ago(pr["merged_minutes"])
    return {"created_at": created, "updated_at": merged or created,
            "closed_at": merged, "merged_at": merged}


def _ref(org: Org, repo: dict, ref: str, sha: str) -> dict:
    return {"ref": ref, "sha": sha,
            "repo": {"full_name": repo["full_name"], "description": repo["description"]}}


def pr_minimal(org: Org, repo: dict, pr: dict, detailed: bool = False) -> dict:
    t = _pr_times(org, pr)
    out = {
        "number": pr["number"], "title": pr["title"], "body": pr["body"],
        "state": pr["state"], "draft": pr["draft"], "merged": pr["merged_minutes"] is not None,
        "html_url": f"{HTML}/{repo['full_name']}/pull/{pr['number']}",
        "user": _user(pr["user"]),
        "labels": [{"name": label} for label in pr["labels"]] or None,
        "head": _ref(org, repo, pr["head_ref"], pr["head_sha"]),
        "base": _ref(org, repo, pr["base_ref"], pr["base_sha"]),
        "created_at": t["created_at"], "updated_at": t["updated_at"],
        "closed_at": t["closed_at"], "merged_at": t["merged_at"],
    }
    if detailed:
        out.update({
            "mergeable_state": "unknown" if out["merged"] else "clean",
            "additions": sum(f["additions"] for f in pr["files"]),
            "deletions": sum(f["deletions"] for f in pr["files"]),
            "changed_files": len(pr["files"]),
            "commits": len(pr["commits"]), "comments": 0,
        })
    return {k: v for k, v in out.items() if v is not None}


def pr_search_item(org: Org, repo: dict, pr: dict) -> dict:
    t = _pr_times(org, pr)
    api = f"{API}/repos/{repo['full_name']}"
    item = {
        "id": _num(repo["name"], pr["number"], digits=10),
        "number": pr["number"], "state": pr["state"], "locked": False,
        "title": pr["title"], "body": pr["body"],
        "author_association": "MEMBER", "user": _search_user(pr["user"]),
        "labels": [{"name": label, "color": "ededed"} for label in pr["labels"]],
        "comments": 0,
        "created_at": t["created_at"], "updated_at": t["updated_at"],
        "closed_at": t["closed_at"],
        "url": f"{api}/issues/{pr['number']}",
        "html_url": f"{HTML}/{repo['full_name']}/pull/{pr['number']}",
        "repository_url": api,
        "pull_request": {
            "url": f"{api}/pulls/{pr['number']}",
            "html_url": f"{HTML}/{repo['full_name']}/pull/{pr['number']}",
            "diff_url": f"{HTML}/{repo['full_name']}/pull/{pr['number']}.diff",
            "patch_url": f"{HTML}/{repo['full_name']}/pull/{pr['number']}.patch",
            **({"merged_at": t["merged_at"]} if t["merged_at"] else {}),
        },
        "draft": pr["draft"],
    }
    if not item["labels"]:
        del item["labels"]
    return item


def commit_obj(repo: dict, commit: dict, detail: Optional[str] = None) -> dict:
    out = {
        "sha": commit["sha"],
        "html_url": f"{HTML}/{repo['full_name']}/commit/{commit['sha']}",
        "commit": {"message": commit["message"], "author": commit["author"],
                   "committer": commit["committer"]},
    }
    # Persona addresses are not linked to GitHub accounts, so GitHub reports
    # no author login - only the rebase-merge committer is a real account.
    if commit["committer"]["email"] == "noreply@github.com":
        out["committer"] = _user("web-flow")
    if detail and detail != "none":
        adds = sum(f["additions"] for f in commit["files"])
        dels = sum(f["deletions"] for f in commit["files"])
        out["stats"] = {"additions": adds, "deletions": dels, "total": adds + dels}
        out["files"] = [
            {"filename": f["filename"], "status": f["status"], "additions": f["additions"],
             "deletions": f["deletions"], "changes": f["additions"] + f["deletions"],
             **({"patch": f["patch"]} if detail == "full_patch" else {})}
            for f in commit["files"]
        ]
    return out


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def search_pull_requests(org: Org, a: dict) -> Any:
    query = a.get("query", "")
    if a.get("owner") and a.get("repo"):
        query += f" repo:{a['owner']}/{a['repo']}"
    filters: list[Callable[[dict, dict], bool]] = []
    terms: list[str] = []
    fields_in = ("title", "body")
    for tok in _tokens(query):
        key, sep, val = tok.partition(":")
        key = key.lower()
        if not sep or not val:
            terms.append(tok.lower())
            continue
        v = val.lower()
        if key in ("org", "user", "owner"):
            if v != org.name.lower():
                return {"total_count": 0, "incomplete_results": False, "search_type": "lexical", "items": []}
        elif key == "repo":
            filters.append(lambda r, p, v=v: r["full_name"].lower() == v)
        elif key == "is":
            if v == "merged":
                filters.append(lambda r, p: p["merged_minutes"] is not None)
            elif v == "unmerged":
                filters.append(lambda r, p: p["merged_minutes"] is None and p["state"] == "closed")
            elif v in ("open", "closed"):
                filters.append(lambda r, p, v=v: p["state"] == v)
            elif v == "draft":
                filters.append(lambda r, p: p["draft"])
        elif key == "state":
            filters.append(lambda r, p, v=v: p["state"] == v)
        elif key == "author":
            filters.append(lambda r, p, v=v: p["user"].lower() == v)
        elif key == "label":
            filters.append(lambda r, p, v=v: v in [label.lower() for label in p["labels"]])
        elif key in ("head", "base"):
            filters.append(lambda r, p, k=key, v=val: p[f"{k}_ref"] == v)
        elif key in ("merged", "created", "updated", "closed"):
            test = _date_filter(val)
            field = {"merged": "merged_at", "created": "created_at",
                     "updated": "updated_at", "closed": "closed_at"}[key]
            filters.append(lambda r, p, t=test, f=field: t(_pr_times(org, p)[f]))
        elif key == "in":
            fields_in = tuple(x for x in val.lower().split(",") if x in ("title", "body")) or fields_in
        elif key in ("type", "is"):
            pass
        else:
            terms.append(tok.lower())

    hits = []
    for repo in org.repos.values():
        for pr in repo["pulls"]:
            if not all(f(repo, pr) for f in filters):
                continue
            hay = " ".join((pr.get(f) or "") for f in fields_in).lower()
            if all(t in hay for t in terms):
                hits.append((repo, pr))

    sort_key = (a.get("sort") or "updated").lower()
    field = "created_at" if sort_key == "created" else "updated_at"
    hits.sort(key=lambda rp: _pr_times(org, rp[1])[field] or "",
              reverse=(a.get("order") or "desc") != "asc")
    items = [_pick(pr_search_item(org, r, p), a.get("fields"))
             for r, p in _paginate(hits, a.get("page"), a.get("perPage"))]
    return {"total_count": len(hits), "incomplete_results": False,
            "search_type": "lexical", "items": items}


def list_pull_requests(org: Org, a: dict) -> Any:
    repo = org.repo(a["owner"], a["repo"])
    state = (a.get("state") or "open").lower()
    pulls = [p for p in repo["pulls"] if state == "all" or p["state"] == state]
    if a.get("head"):
        branch = a["head"].split(":", 1)[-1]
        pulls = [p for p in pulls if p["head_ref"] == branch]
    if a.get("base"):
        pulls = [p for p in pulls if p["base_ref"] == a["base"]]
    field = "updated_at" if (a.get("sort") or "created") == "updated" else "created_at"
    pulls.sort(key=lambda p: _pr_times(org, p)[field] or "",
               reverse=(a.get("direction") or "desc") != "asc")
    return [_pick(pr_minimal(org, repo, p), a.get("fields"))
            for p in _paginate(pulls, a.get("page"), a.get("perPage"))]


def pull_request_read(org: Org, a: dict) -> Any:
    repo, pr = org.pr(a["owner"], a["repo"], a["pullNumber"])
    method = a.get("method", "get")
    if method == "get":
        return pr_minimal(org, repo, pr, detailed=True)
    if method == "get_diff":
        return pr["diff"]
    if method == "get_files":
        files = [{"filename": f["filename"], "status": f["status"], "additions": f["additions"],
                  "deletions": f["deletions"], "changes": f["additions"] + f["deletions"],
                  "patch": f["patch"]} for f in pr["files"]]
        return _paginate(files, a.get("page"), a.get("perPage"))
    if method == "get_commits":
        return [{"sha": c["sha"], "html_url": f"{HTML}/{repo['full_name']}/commit/{c['sha']}",
                 "message": c["message"], "author": c["author"]} for c in pr["commits"]]
    if method == "get_check_runs":
        start = org.ago((pr["merged_minutes"] or pr["created_minutes"]) + 6)
        runs = []
        for i, (name, conclusion) in enumerate(pr["checks"]):
            run_id = _num(repo["name"], pr["number"], name, digits=11)
            url = f"{HTML}/{repo['full_name']}/actions/runs/{run_id}"
            run = {"id": run_id, "name": name, "status": "completed", "conclusion": conclusion,
                   "html_url": url, "details_url": url, "started_at": start}
            if conclusion != "skipped":
                run["completed_at"] = org.ago((pr["merged_minutes"] or pr["created_minutes"]) + 3 - i)
            runs.append(run)
        return {"total_count": len(runs), "check_runs": runs}
    if method == "get_status":
        return {"state": "pending" if not pr["checks"] else "success", "sha": pr["head_sha"],
                "total_count": 0, "statuses": []}
    if method in ("get_reviews", "get_comments"):
        return []
    if method == "get_review_comments":
        return {"reviewThreads": [], "pageInfo": {"hasNextPage": False, "endCursor": ""}, "totalCount": 0}
    raise ValueError(f"unknown method: {method}")


def _code_terms(query: str) -> tuple[list[list[str]], list[str], dict[str, list[str]]]:
    """Split a code-search query into OR-groups of required terms, NOT terms and qualifiers."""
    quals: dict[str, list[str]] = {}
    groups: list[list[str]] = [[]]
    negate, nots = False, []
    for tok in _tokens(query):
        key, sep, val = tok.partition(":")
        if sep and val and key.lower() in ("org", "user", "repo", "path", "filename", "extension",
                                           "language", "in", "size", "is"):
            quals.setdefault(key.lower(), []).append(val)
        elif tok == "OR":
            groups.append([])
        elif tok == "NOT":
            negate = True
        elif tok == "AND":
            continue
        else:
            (nots if negate else groups[-1]).append(tok.lower())
            negate = False
    return [g for g in groups if g] or [[]], nots, quals


EXT_LANG = {"java": "java", "kotlin": "kt", "python": "py", "go": "go", "typescript": "ts",
            "hcl": "tf", "terraform": "tf", "yaml": "yaml", "json": "json", "markdown": "md",
            "scala": "scala", "xml": "xml", "shell": "sh", "properties": "properties"}


def search_code(org: Org, a: dict) -> Any:
    groups, nots, q = _code_terms(a.get("query", ""))
    for owner in q.get("org", []) + q.get("user", []):
        if owner.lower() != org.name.lower():
            return {"total_count": 0, "incomplete_results": False, "items": []}
    in_path = "path" in [v.lower() for v in q.get("in", [])]
    hits = []
    for repo in org.repos.values():
        if q.get("repo") and repo["full_name"].lower() not in [r.lower() for r in q["repo"]]:
            continue
        for path, f in sorted(repo["files"].items()):
            name = path.rsplit("/", 1)[-1]
            if any(not path.startswith(p.strip("/")) for p in q.get("path", [])):
                continue
            if any(name != fn for fn in q.get("filename", [])):
                continue
            if any(not name.endswith("." + e.lstrip(".")) for e in q.get("extension", [])):
                continue
            if any(not name.endswith("." + EXT_LANG.get(lang.lower(), lang.lower())) for lang in q.get("language", [])):
                continue
            hay = path.lower() if in_path else f["text"].lower()
            if any(n in hay for n in nots):
                continue
            if not any(all(t in hay for t in g) for g in groups):
                continue
            hits.append((repo, path, f))
    items = []
    for repo, path, f in _paginate(hits, a.get("page"), a.get("perPage")):
        first = next((t for g in groups for t in g), "")
        items.append(_pick({
            "name": path.rsplit("/", 1)[-1], "path": path, "sha": f["sha"],
            "repository": repo["full_name"],
            "text_matches": [_fragment(repo, path, f["text"], first)] if first else [],
        }, a.get("fields")))
    return {"total_count": len(hits), "incomplete_results": False, "items": items}


def _fragment(repo: dict, path: str, text: str, term: str) -> dict:
    lines = text.splitlines()
    idx = next((i for i, line in enumerate(lines) if term in line.lower()), 0)
    frag = "\n".join(lines[max(0, idx - 2): idx + 3])
    pos = frag.lower().find(term)
    return {
        "object_url": f"{API}/repos/{repo['full_name']}/contents/{path}",
        "object_type": "FileContent", "property": "content", "fragment": frag,
        "matches": [{"text": frag[pos:pos + len(term)], "indices": [pos, pos + len(term)]}] if pos >= 0 else [],
    }


def get_file_contents(org: Org, a: dict) -> Any:
    repo = org.repo(a["owner"], a["repo"])
    path = (a.get("path") or "/").strip("/")
    files = dict((p, f["text"]) for p, f in repo["files"].items())
    shas = {p: f["sha"] for p, f in repo["files"].items()}
    ref = a.get("ref") or ""
    m = re.match(r"refs/pull/(\d+)/head$", ref)
    if m:
        _, pr = org.pr(a["owner"], a["repo"], int(m.group(1)))
        files.update(pr.get("head_files", {}))
    if path in files:
        return [f"successfully downloaded text file (SHA: {shas.get(path, '')})", files[path]]
    prefix = path + "/" if path else ""
    children: dict[str, dict] = {}
    for p in files:
        if not p.startswith(prefix):
            continue
        head, _, rest = p[len(prefix):].partition("/")
        entry_path = prefix + head
        if rest:
            children.setdefault(head, {"type": "dir", "size": 0, "name": head, "path": entry_path,
                                       "sha": ""})
        else:
            children[head] = {"type": "file", "size": len(files[p].encode()), "name": head,
                              "path": entry_path, "sha": shas.get(p, "")}
    if not children:
        raise NotFound(f"failed to get file contents {repo['full_name']}/{path}: 404 Not Found")
    entries = []
    for child in sorted(children.values(), key=lambda c: (c["type"] != "dir", c["name"])):
        child.update({
            "url": f"{API}/repos/{repo['full_name']}/contents/{child['path']}?ref=main",
            "git_url": f"{API}/repos/{repo['full_name']}/git/{'trees' if child['type'] == 'dir' else 'blobs'}/{child['sha']}",
            "html_url": f"{HTML}/{repo['full_name']}/{'tree' if child['type'] == 'dir' else 'blob'}/main/{child['path']}",
        })
        entries.append(_pick(child, a.get("fields")))
    return entries


def list_commits(org: Org, a: dict) -> Any:
    repo = org.repo(a["owner"], a["repo"])
    commits = repo["commits"]
    if a.get("path"):
        p = a["path"].strip("/")
        commits = [c for c in commits
                   if any(f["filename"] == p or f["filename"].startswith(p + "/") for f in c["files"])]
    if a.get("author"):
        who = a["author"].lower()
        commits = [c for c in commits
                   if who in (c["author"]["email"].lower(), c["author"]["name"].lower())]
    if a.get("since"):
        lo = _parse_when(a["since"])
        commits = [c for c in commits if lo is None or _parse_when(c["committer"]["date"]) >= lo]
    if a.get("until"):
        hi = _parse_when(a["until"], end_of_day=True)
        commits = [c for c in commits if hi is None or _parse_when(c["committer"]["date"]) <= hi]
    commits = sorted(commits, key=lambda c: _parse_when(c["committer"]["date"]), reverse=True)
    return [_pick(commit_obj(repo, c), a.get("fields"))
            for c in _paginate(commits, a.get("page"), a.get("perPage"))]


def get_commit(org: Org, a: dict) -> Any:
    repo = org.repo(a["owner"], a["repo"])
    sha = (a.get("sha") or "").lower()
    if sha in ("main", "head", "refs/heads/main"):
        commit = max(repo["commits"], key=lambda c: _parse_when(c["committer"]["date"]))
    else:
        pool = repo["commits"] + [c for p in repo["pulls"] for c in p["commits"]]
        commit = next((c for c in pool if len(sha) >= 7 and c["sha"].startswith(sha)), None)
        if commit is None:
            raise NotFound(f"failed to get commit {sha} in {repo['full_name']}: 404 Not Found")
    return commit_obj(repo, commit, detail=a.get("detail") or "stats")


def search_repositories(org: Org, a: dict) -> Any:
    terms, topics, langs, fields_in = [], [], [], ("name", "description", "topics")
    for tok in _tokens(a.get("query", "")):
        key, sep, val = tok.partition(":")
        key = key.lower()
        if sep and val and key in ("org", "user"):
            if val.lower() != org.name.lower():
                return {"total_count": 0, "incomplete_results": False, "items": []}
        elif sep and val and key == "topic":
            topics.append(val.lower())
        elif sep and val and key == "language":
            langs.append(val.lower())
        elif sep and val and key == "in":
            fields_in = tuple(val.lower().split(","))
        elif sep and val and key in ("is", "archived", "fork", "stars"):
            continue
        else:
            terms.append(tok.lower())
    hits = []
    for repo in org.repos.values():
        if any(t not in repo["topics"] for t in topics):
            continue
        if langs and (repo.get("language") or "").lower() not in langs:
            continue
        hay = " ".join([
            repo["name"] if "name" in fields_in else "",
            repo["description"] if "description" in fields_in else "",
            " ".join(repo["topics"]) if "topics" in fields_in else "",
            repo["files"].get("README.md", {}).get("text", "") if "readme" in fields_in else "",
        ]).lower()
        if all(t in hay for t in terms):
            hits.append(repo)
    items = []
    for repo in _paginate(hits, a.get("page"), a.get("perPage")):
        last = _iso(max(_parse_when(c["committer"]["date"]) for c in repo["commits"]))
        items.append({
            "id": _num(repo["name"], digits=9), "name": repo["name"],
            "full_name": repo["full_name"], "description": repo["description"],
            "html_url": f"{HTML}/{repo['full_name']}", "language": repo.get("language"),
            "stargazers_count": 0, "forks_count": 0,
            "open_issues_count": sum(1 for p in repo["pulls"] if p["state"] == "open"),
            "updated_at": last, "created_at": repo["created_at"], "topics": repo["topics"],
            "private": True, "fork": False, "archived": False, "default_branch": "main",
        })
    return {"total_count": len(hits), "incomplete_results": False, "items": items}


HANDLERS: dict[str, Callable[[Org, dict], Any]] = {
    "search_pull_requests": search_pull_requests,
    "list_pull_requests": list_pull_requests,
    "pull_request_read": pull_request_read,
    "search_code": search_code,
    "get_file_contents": get_file_contents,
    "list_commits": list_commits,
    "get_commit": get_commit,
    "search_repositories": search_repositories,
}


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


def load_tool_definitions() -> list[types.Tool]:
    defs = json.loads(TOOLS_FILE.read_text())["tools"]
    return [types.Tool(name=name, description=d["description"], inputSchema=d["inputSchema"])
            for name, d in defs.items() if name in HANDLERS]


def call(snapshot: dict, name: str, arguments: dict) -> list[types.TextContent]:
    """Run one tool against a freshly-timed view of the snapshot."""
    org = Org(json.loads(json.dumps(snapshot)))  # timestamps resolve against "now"
    result = HANDLERS[name](org, arguments or {})
    parts = result if isinstance(result, list) and result and all(isinstance(x, str) for x in result) \
        else [result]
    return [types.TextContent(type="text",
                              text=p if isinstance(p, str) else json.dumps(p, ensure_ascii=False))
            for p in parts]


def build_server() -> Server:
    snapshot = json.loads(_snapshot_path().read_text())
    tools = load_tool_definitions()
    server = Server("github-stub")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        if name not in HANDLERS:
            raise ValueError(f"unknown tool: {name}")
        try:
            return call(snapshot, name, arguments)
        except NotFound as exc:
            raise ValueError(str(exc)) from None

    return server


async def _main() -> None:
    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    logger.info("github MCP stub starting (snapshot: %s)", _snapshot_path().name)
    asyncio.run(_main())
