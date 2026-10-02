"""Tests for the Confluence knowledge base: the catalogue, and the read tools.

Two things are load-bearing here. The catalogue's planted facts only work if
the agent can reach them - so the alert's runbook link must resolve and the
obvious searches must find the right pages - and only if the agent is never
TOLD which pages are stale, so the brief-only metadata must never reach a
tool result.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from agent.integrations import IntegrationError
from agent.mcp_servers import confluence as live
from harness import scenarios
from harness.stubs import _kb_pages as kb
from harness.stubs import confluence_mcp as stub

STUB = stub.build()


def _call(server, tool, **args) -> str:
    """Call a tool the way an MCP client would; returns its text."""
    content, _ = asyncio.run(server.call_tool(tool, args))
    return content[0].text


def _get_page(page) -> str:
    return _call(STUB, "get_page", page=page)


def _search_pages(query, limit=5) -> str:
    return _call(STUB, "search_pages", query=query, limit=limit)


def _alert():
    return scenarios.load("consumer-lag").incident()


def _search(query, limit=5):
    return json.loads(_search_pages(query, limit))["results"]


def _titles(query, limit=5):
    return [r["title"] for r in _search(query, limit)]


# ---------------------------------------------------------------------------
# Catalogue invariants
# ---------------------------------------------------------------------------


def test_no_page_postdates_the_culprit_merges():
    """The culprit PR merges on 2026-05-07; a later page gives the game away."""
    assert max(p.reviewed for p in kb.PAGES) <= "2026-05-06"


def test_titles_are_unique():
    titles = [p.title.lower() for p in kb.PAGES]
    assert len(titles) == len(set(titles))


def test_every_misleading_page_documents_what_is_wrong():
    for page in kb.PAGES:
        assert bool(page.planted) == (page.role in ("stale", "red-herring")), page.slug


def test_pages_link_to_the_real_space():
    """The pages exist in the real DSS26 space; stub links must point at them."""
    page = kb.BY_SLUG["rb-consumer-lag"]
    assert page.url == (
        "https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3979280388/"
        "Runbook+Consumer+lag+critical"
    )
    assert {p.title for p in kb.PAGES} <= kb.PAGE_IDS.keys()
    assert len(set(kb.PAGE_IDS.values())) == len(kb.PAGE_IDS)


def test_the_alert_links_the_runbook_by_its_real_id():
    runbook_url = _alert()["incident"]["custom_details"]["runbook_url"]
    assert runbook_url == kb.BY_SLUG["rb-consumer-lag"].url


# ---------------------------------------------------------------------------
# get_page
# ---------------------------------------------------------------------------


def test_the_alerts_runbook_link_resolves():
    url = _alert()["incident"]["custom_details"]["runbook_url"]
    assert json.loads(_get_page(url))["title"] == "Runbook: Consumer lag critical"


@pytest.mark.parametrize(
    "ref",
    [
        lambda p: p.page_id,
        lambda p: p.url,
        lambda p: p.title,
        lambda p: p.title.upper(),
        lambda p: "Consumer lag critical",
    ],
)
def test_get_page_accepts_ids_urls_and_titles(ref):
    page = kb.BY_SLUG["rb-consumer-lag"]
    out = json.loads(_get_page(ref(page)))
    assert (out["id"], out["title"], out["url"]) == (page.page_id, page.title, page.url)


def test_page_body_carries_the_review_date_the_agent_judges_by():
    out = json.loads(_get_page("Runbook: Consumer lag critical"))
    assert out["last_modified"] == "2024-03-12"
    assert "Last reviewed: 2024-03-12" in out["body"]
    assert "fraud-scoring-consumer" in out["body"]


def test_brief_only_metadata_never_reaches_the_agent():
    """The agent must work out a page is stale; nothing may tell it."""
    for page in kb.PAGES:
        served = _get_page(page.page_id) + _search_pages(page.title, 10)
        assert "stale" not in served.lower() or "stale" in page.body().lower()
        if page.planted:
            assert page.planted.conclusion not in served
            assert page.planted.truth not in served


def test_unknown_page_is_an_error_payload_with_a_way_forward():
    out = json.loads(_get_page("no such page anywhere"))
    assert out["error"] == "page not found"
    assert "search_pages" in out["hint"]


# ---------------------------------------------------------------------------
# search_pages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, expected",
    [
        ("consumer lag fraud-decisioning-engine", "Runbook: Consumer lag critical"),
        ("fraud-decisioning-svc", "Service: fraud-decisioning-svc"),
        ("schema compatibility", "Schema evolution policy for card events"),
        ("schema rollback", "Runbook: Roll back an incompatible schema version"),
        ("fraud-scoring-consumer", "ADR-0011: Rename fraud-scoring to fraud-decisioning"),
    ],
)
def test_the_obvious_search_finds_the_planted_page_first(query, expected):
    assert _titles(query)[0] == expected


def test_past_incidents_with_the_same_symptom_are_findable():
    assert "INC-2025-03-18-002: fraud-decisioning lag during a rebalance storm" in _titles(
        "consumer lag fraud-decisioning"
    )
    assert "INC-2024-09-12-003: Incompatible schema on cards.clearing.matched.v1" in _titles(
        "incompatible schema"
    )


def test_matching_is_by_whole_word():
    """'ci' must not match inside 'decisioning'."""
    for hit in _search("ci", 10):
        assert "decisioning" not in hit["title"].lower() or "ci" in hit["excerpt"].lower().split()


def test_search_result_shape_and_limit():
    hits = _search("runbook", 2)
    assert len(hits) == 2
    assert set(hits[0]) == {"id", "title", "url", "last_modified", "excerpt"}
    assert _search("zzzz-no-such-word") == []


# ---------------------------------------------------------------------------
# Live back-end
# ---------------------------------------------------------------------------


def _fake_live(monkeypatch, responses, space="CARDS"):
    from agent.integrations import confluence as cf

    calls = []

    def fake_request(method, path, params=None, json=None):
        calls.append({"method": method, "path": path, "params": params})
        for prefix, value in responses.items():
            if path.startswith(prefix):
                return value(params) if callable(value) else value
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(cf, "_request", fake_request)
    monkeypatch.setattr(cf, "CONFLUENCE_SPACE", space)
    monkeypatch.setattr(cf, "CONFLUENCE_BASE_URL", "https://x.atlassian.net/wiki")
    return cf, calls


_V1_HIT = {
    "content": {"id": "42", "type": "page", "title": "Runbook: Consumer lag critical",
                "_links": {"webui": "/spaces/CARDS/pages/42/Runbook"}},
    "excerpt": "First response when the @@@hl@@@lag@@@endhl@@@ alert fires",
    "lastModified": "2026-09-30T10:00:00.000Z",
}


def test_live_search_is_scoped_quoted_and_projected(monkeypatch):
    cf, calls = _fake_live(monkeypatch, {"/rest/api/search": {"results": [_V1_HIT]}})
    out = cf.search_pages('lag "critical"', 3)

    cql = calls[0]["params"]["cql"]
    assert cql == 'space = "CARDS" AND type = page AND text ~ "lag \\"critical\\""'
    assert out["results"] == [{
        "id": "42",
        "title": "Runbook: Consumer lag critical",
        "url": "https://x.atlassian.net/wiki/spaces/CARDS/pages/42/Runbook",
        "last_modified": "2026-09-30T10:00:00.000Z",
        "excerpt": "First response when the lag alert fires",
    }]


def test_live_search_without_a_pinned_space_is_unscoped(monkeypatch):
    cf, calls = _fake_live(monkeypatch, {"/rest/api/search": {"results": []}}, space="")
    cf.search_pages("lag")
    assert not calls[0]["params"]["cql"].startswith("space")


def test_live_empty_query_is_refused(monkeypatch):
    cf, _ = _fake_live(monkeypatch, {})
    with pytest.raises(IntegrationError):
        cf.search_pages("   ")


_V2_PAGE = {
    "id": "42",
    "title": "Runbook: Consumer lag critical",
    "version": {"createdAt": "2026-09-30T10:00:00.000Z", "number": 3},
    "body": {"storage": {"value": "<table><tr><th>Last reviewed</th><td>2024-03-12</td></tr></table>"
                                  "<h2>Steps</h2><ul><li>Scale to 6 replicas</li></ul>"}},
    "_links": {"webui": "/spaces/CARDS/pages/42/Runbook", "base": "https://x.atlassian.net/wiki"},
}


@pytest.mark.parametrize(
    "ref, searches",
    [
        ("42", 0),
        ("https://x.atlassian.net/wiki/spaces/CARDS/pages/42/Runbook", 0),
        # The demo alerts' runbook links have no numeric id: looked up by title words.
        ("https://dss26.atlassian.net/wiki/spaces/CARDS/pages/Runbooks/Consumer-Lag-Critical", 1),
    ],
)
def test_live_get_page_resolves_ids_urls_and_alert_links(monkeypatch, ref, searches):
    cf, calls = _fake_live(monkeypatch, {
        "/rest/api/search": {"results": [_V1_HIT]},
        "/api/v2/pages/42": _V2_PAGE,
    })
    out = cf.get_page(ref)

    search_calls = [c for c in calls if c["path"] == "/rest/api/search"]
    assert len(search_calls) == searches
    if searches:
        assert 'title ~ "Consumer Lag Critical"' in search_calls[0]["params"]["cql"]
    assert out["url"] == "https://x.atlassian.net/wiki/spaces/CARDS/pages/42/Runbook"
    assert "Last reviewed | 2024-03-12" in out["body"]
    assert "## Steps" in out["body"] and "- Scale to 6 replicas" in out["body"]


def test_live_get_page_with_no_match_says_how_to_recover(monkeypatch):
    cf, _ = _fake_live(monkeypatch, {"/rest/api/search": {"results": []}})
    with pytest.raises(IntegrationError) as exc:
        cf.get_page("Runbook: does not exist")
    assert "search_pages" in (exc.value.hint or "")


def test_live_get_page_truncates_huge_pages(monkeypatch):
    big = dict(_V2_PAGE, body={"storage": {"value": "<p>" + "x" * 30_000 + "</p>"}})
    cf, _ = _fake_live(monkeypatch, {"/api/v2/pages/42": big})
    assert cf.get_page("42")["body"].endswith("[page truncated]")


def test_live_read_errors_come_back_as_data(monkeypatch):
    from agent.integrations import confluence as cf

    def boom(*_args, **_kwargs):
        raise IntegrationError("boom", system="confluence")

    monkeypatch.setattr(cf, "search_pages", boom)
    monkeypatch.setattr(cf, "get_page", boom)
    server = live.build_server(live.LiveConfluence())
    assert json.loads(_call(server, "search_pages", query="lag"))["error"] == "boom"
    assert json.loads(_call(server, "get_page", page="42"))["page"] == "42"


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_the_runner_hands_triage_exactly_the_read_tools():
    runner = pytest.importorskip("agent.runner")
    names = {t.name for t in asyncio.run(STUB.list_tools())}
    assert runner.KB_READ_TOOLS <= names
    assert names - runner.KB_READ_TOOLS == {"create_page"}


def test_prompts_only_mention_the_kb_when_it_is_on():
    from agent.prompts import load_prompt

    base = dict(MCP_PAGERDUTY=True, NO_PAGERDUTY=False)
    assert "get_page" in load_prompt("triage", KB=True, **base)
    assert "knowledge" not in load_prompt("triage", KB=False, **base)

    rep = dict(MCP_CONFLUENCE=True, NO_CONFLUENCE=False, MCP_SLACK=True, NO_SLACK=False,
               NO_PUBLISHING=False, SKILLS=False, SKILL_NAMES="")
    assert "## Documentation follow-ups" in load_prompt("reporter", KB=True, **rep)
    assert "Documentation follow-ups" not in load_prompt("reporter", KB=False, **rep)
