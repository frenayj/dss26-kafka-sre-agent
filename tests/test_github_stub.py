"""Tests for the GitHub MCP stub (``harness.stubs.github_mcp``).

The stub stands in for GitHub's official MCP server in ``GITHUB_MODE=stub``,
so the things worth pinning are the ones the model and the UI rely on:

* the tool surface is the official server's, name for name;
* search behaves like GitHub search (qualifiers, terms, date windows), so the
  forensics agent's queries work the same way in both modes;
* relative timestamps resolve against "now", so a stub run looks like today;
* unknown repos and files are errors, as on GitHub - never invented content.

They run against a small synthetic snapshot, not the generated org, so they
do not move when the org's declarations change.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("mcp")

from harness.stubs import github_mcp as g  # noqa: E402

NOW = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)


def _commit(sha, msg, files, date=None, minutes=None, name="Marta Silva"):
    who = {"name": name, "email": "marta.silva@dss26bank.example", "date": date or "2026-03-18T17:05:00+01:00"}
    return {"sha": sha, "message": msg, "author": dict(who), "committer": dict(who),
            "files": files, "relative_minutes": minutes}


def _pr(number, title, *, merged=None, created=60, state="closed", files=(), labels=()):
    return {
        "number": number, "key": f"k{number}", "title": title, "body": f"body of {title}",
        "state": state, "draft": False, "labels": list(labels), "user": "ravi-iyer",
        "head_ref": f"branch-{number}", "base_ref": "main", "head_sha": f"{number:040d}",
        "base_sha": "0" * 40, "created_minutes": created, "merged_minutes": merged,
        "commits": [_commit(f"{number:040x}", title, list(files), minutes=(merged or created) + 1)],
        "files": list(files), "diff": f"diff --git a/x b/x\n+change {number}\n",
        "head_files": {}, "checks": [["build", "success"], ["schema-compat / compat", "skipped"]],
    }


AVSC = "src/main/avro/cards.authorisation.requested.v1.avsc"
FILE = {"filename": AVSC, "status": "modified",
        "additions": 1, "deletions": 1, "patch": "@@ -1 +1 @@\n-a\n+b"}

SNAPSHOT = {
    "org": "dss26-org",
    "repos": [{
        "name": "merchant-gateway", "full_name": "dss26-org/merchant-gateway",
        "description": "Merchant and acquirer edge", "topics": ["kafka", "schema-registry"],
        "team": "payments-edge", "language": "Java", "created_at": "2024-02-27T10:12:00+01:00",
        "files": {
            "README.md": {"sha": "a" * 40, "size": 19, "text": "# merchant-gateway\n"},
            AVSC: {
                "sha": "b" * 40, "size": 104,
                "text": '{"type": "record", "name": "AuthorisationRequested",\n'
                        ' "fields": [{"name": "amount", "type": "double"}]}\n'},
        },
        "commits": [
            _commit("c" * 40, "ci(release): register the schema on merge", [
                {"filename": ".github/workflows/release.yml", "status": "modified",
                 "additions": 2, "deletions": 4, "patch": "@@"}]),
            _commit("d" * 40, "chore: bootstrap", [FILE], date="2024-02-27T10:12:00+01:00"),
        ],
        "pulls": [
            _pr(1, "fix(api): reject unknown currency codes", merged=300, created=320,
                files=[FILE], labels=["api"]),
            _pr(2, "feat(auth-events): publish amount as a decimal string", merged=12, created=30,
                files=[FILE], labels=["schema", "tier-1"]),
            _pr(3, "docs: schema change checklist", state="open", created=9000),
        ],
    }],
}


def call(name, args):
    org = g.Org(json.loads(json.dumps(SNAPSHOT)), now=NOW)
    return g.HANDLERS[name](org, args)


def test_tool_surface_is_the_official_servers():
    names = {t.name for t in g.load_tool_definitions()}
    assert names == set(g.HANDLERS) == {
        "search_pull_requests", "list_pull_requests", "pull_request_read", "search_code",
        "get_file_contents", "list_commits", "get_commit", "search_repositories",
    }


def test_merged_window_search_returns_the_days_merges_newest_first():
    since = (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = call("search_pull_requests", {"query": f"org:dss26-org is:merged merged:>={since}"})
    assert [i["number"] for i in out["items"]] == [2]
    assert out["items"][0]["pull_request"]["merged_at"] == "2026-10-01T14:48:00Z"

    out = call("search_pull_requests", {"query": "org:dss26-org is:merged"})
    assert [i["number"] for i in out["items"]] == [2, 1]


def test_search_terms_labels_and_state():
    assert call("search_pull_requests", {"query": "org:dss26-org decimal"})["total_count"] == 1
    assert call("search_pull_requests", {"query": "org:dss26-org label:tier-1"})["total_count"] == 1
    assert call("search_pull_requests", {"query": "org:dss26-org is:open"})["total_count"] == 1
    assert call("search_pull_requests", {"query": "org:someone-else is:merged"})["total_count"] == 0


def test_pull_request_read_methods():
    args = {"owner": "dss26-org", "repo": "merchant-gateway", "pullNumber": 2}
    assert call("pull_request_read", {**args, "method": "get_diff"}).startswith("diff --git")
    pr = call("pull_request_read", {**args, "method": "get"})
    assert pr["merged"] is True and pr["changed_files"] == 1 and pr["user"]["login"] == "ravi-iyer"
    checks = call("pull_request_read", {**args, "method": "get_check_runs"})["check_runs"]
    assert {c["name"]: c["conclusion"] for c in checks}["schema-compat / compat"] == "skipped"


def test_code_search_matches_content_and_qualifiers():
    out = call("search_code", {"query": '"AuthorisationRequested" org:dss26-org'})
    assert [i["path"] for i in out["items"]] == [AVSC]
    assert "AuthorisationRequested" in out["items"][0]["text_matches"][0]["fragment"]
    assert call("search_code", {"query": "AuthorisationRequested path:docs org:dss26-org"})["total_count"] == 0


def test_file_contents_are_two_parts_and_directories_list():
    parts = call("get_file_contents", {"owner": "dss26-org", "repo": "merchant-gateway",
                                       "path": "README.md"})
    assert parts[0].startswith("successfully downloaded text file") and parts[1].startswith("#")
    listing = call("get_file_contents", {"owner": "dss26-org", "repo": "merchant-gateway",
                                         "path": "src/main"})
    assert [(e["name"], e["type"]) for e in listing] == [("avro", "dir")]


def test_commits_filter_by_path_and_report_utc_dates():
    out = call("list_commits", {"owner": "dss26-org", "repo": "merchant-gateway",
                                "path": ".github/workflows/release.yml"})
    assert len(out) == 1
    assert out[0]["commit"]["author"]["date"] == "2026-03-18T16:05:00Z"
    full = call("get_commit", {"owner": "dss26-org", "repo": "merchant-gateway",
                               "sha": "ddddddd", "detail": "full_patch"})
    assert full["files"][0]["patch"].startswith("@@")


def test_unknown_repo_is_an_error_not_an_empty_answer():
    with pytest.raises(g.NotFound):
        call("list_commits", {"owner": "dss26-org", "repo": "fraud-decisioning-svc"})
    with pytest.raises(g.NotFound):
        call("get_file_contents", {"owner": "dss26-org", "repo": "merchant-gateway",
                                   "path": "nope.txt"})


def test_shipped_snapshot_loads_when_present():
    try:
        path = g._snapshot_path()
    except FileNotFoundError:
        pytest.skip("snapshot not generated")
    org = g.Org(json.loads(path.read_text()))
    assert org.name == "dss26-org" and org.repos
