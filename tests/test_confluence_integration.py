"""Tests for the Confluence back-end split (fixture vs live).

`create_page` must return the same ack shape in both modes - the reporter
cites `url` in its Slack summary and the UI's CreatePageResult reads
`id/url/space/title/created_at`. Live mode adds the guardrails these tests
pin: the space policy, title dedupe, the dry-run default, and a Markdown
conversion that cannot produce XHTML Confluence would reject.
"""

from __future__ import annotations

import asyncio
import json
import xml.etree.ElementTree as ET

import pytest

from agent.config import resolve_integration_mode
from agent.integrations import IntegrationError

_SPACES = {"results": [{"id": "98304", "key": "SRE"}]}
_NO_PAGES = {"results": []}
_CREATED = {
    "id": "557057",
    "title": "RCA",
    "createdAt": "2026-10-01T09:00:00.000Z",
    "_links": {"webui": "/spaces/SRE/pages/557057/RCA", "base": "https://x.atlassian.net/wiki"},
}


def _fake_confluence(monkeypatch, *, pages=_NO_PAGES, dry_run=False, space="", parent=""):
    """Replace the HTTP layer and return (module, recorded calls)."""
    from agent.integrations import confluence as cf

    calls = []

    def fake_request(method, path, params=None, json=None):
        calls.append({"method": method, "path": path, "params": params, "json": json})
        if path == "/api/v2/spaces":
            return _SPACES if params["keys"] in ("SRE", "SANDBOX") else {"results": []}
        if method == "GET" and path == "/api/v2/pages":
            return pages
        if method == "POST" and path == "/api/v2/pages":
            return _CREATED
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(cf, "_request", fake_request)
    monkeypatch.setattr(cf, "CONFLUENCE_DRY_RUN", dry_run)
    monkeypatch.setattr(cf, "CONFLUENCE_SPACE", space)
    monkeypatch.setattr(cf, "CONFLUENCE_PARENT_PAGE_ID", parent)
    return cf, calls


def _posts(calls):
    return [c for c in calls if c["method"] == "POST"]


# ---------------------------------------------------------------------------
# Mode + credentials
# ---------------------------------------------------------------------------


def test_mode_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("CONFLUENCE_MODE", raising=False)
    assert resolve_integration_mode("confluence") == "stub"


def test_missing_config_names_every_missing_var(monkeypatch):
    from agent.integrations import confluence as cf

    monkeypatch.setattr(cf, "CONFLUENCE_BASE_URL", "https://x.atlassian.net/wiki")
    monkeypatch.setattr(cf, "CONFLUENCE_EMAIL", "")
    monkeypatch.setattr(cf, "CONFLUENCE_API_TOKEN", "")
    with pytest.raises(IntegrationError) as exc:
        cf._check_config()
    assert "CONFLUENCE_EMAIL" in str(exc.value)
    assert "CONFLUENCE_API_TOKEN" in str(exc.value)
    assert "CONFLUENCE_MODE=stub" in (exc.value.hint or "")


# ---------------------------------------------------------------------------
# Markdown -> storage format
# ---------------------------------------------------------------------------


def test_storage_output_is_well_formed_xml_even_with_markup_lookalikes():
    """One stray '<' and Confluence rejects the whole page."""
    pytest.importorskip("markdown")
    from agent.integrations.confluence import markdown_to_storage

    body = (
        "# [P1] lag on <fraud-decisioning-engine>\n\n"
        "## Evidence\n"
        "- lag > 50k & growing (Datadog)\n"
        "- raw: <script>alert(1)</script> &nbsp;&copy; &#169; &bogus;\n\n"
        "| cluster | lag |\n|---|---|\n| prod | 73,412 |\n\n"
        "```\ncompatibility=BACKWARD\n```\n"
    )
    storage = markdown_to_storage(body)

    root = ET.fromstring(f"<root>{storage}</root>")  # raises if malformed
    assert root.find("h1") is not None
    assert root.find("table") is not None
    # Markup lookalikes survive as TEXT, not as elements.
    assert root.find(".//script") is None
    assert "<fraud-decisioning-engine>" in root.find("h1").text
    # HTML entities render as their characters; a made-up one stays literal.
    raw = root.findall(".//li")[1].text
    assert "\u00a0\u00a9 \u00a9 &bogus;" in raw


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def test_dry_run_verifies_the_space_but_creates_nothing(monkeypatch):
    cf, calls = _fake_confluence(monkeypatch, dry_run=True)
    ack = cf.create_page("SRE", "RCA", "# body")

    assert ack["dry_run"] is True
    assert ack["url"] is None
    assert _posts(calls) == []
    # The space lookup is the credential check - it must still happen.
    assert calls[0]["path"] == "/api/v2/spaces"


def test_existing_title_is_returned_not_recreated(monkeypatch):
    """A retried reporter must not hit Confluence's duplicate-title 400."""
    cf, calls = _fake_confluence(monkeypatch, pages={"results": [_CREATED]})
    ack = cf.create_page("SRE", "RCA", "# body")

    assert ack["deduplicated"] is True
    assert ack["url"] == "https://x.atlassian.net/wiki/spaces/SRE/pages/557057/RCA"
    assert _posts(calls) == []


def test_dedupe_wins_over_dry_run(monkeypatch):
    """An already-published page has a real URL worth citing, dry run or not."""
    cf, _ = _fake_confluence(monkeypatch, pages={"results": [_CREATED]}, dry_run=True)
    ack = cf.create_page("SRE", "RCA", "# body")
    assert ack.get("deduplicated") is True
    assert "dry_run" not in ack


def test_space_pin_overrides_the_model_and_says_so(monkeypatch):
    cf, calls = _fake_confluence(monkeypatch, space="SANDBOX", dry_run=True)
    ack = cf.create_page("SRE", "RCA", "# body")

    assert ack["space"] == "SANDBOX"
    assert ack["requested_space"] == "SRE"
    assert calls[0]["params"]["keys"] == "SANDBOX"


def test_unknown_space_fails_with_a_hint(monkeypatch):
    cf, _ = _fake_confluence(monkeypatch)
    with pytest.raises(IntegrationError) as exc:
        cf.create_page("NOPE", "RCA", "# body")
    assert "CONFLUENCE_SPACE" in (exc.value.hint or "")


def test_live_publish_posts_storage_format_under_the_parent(monkeypatch):
    pytest.importorskip("markdown")
    cf, calls = _fake_confluence(monkeypatch, parent="12345")
    ack = cf.create_page("SRE", "RCA", "## Summary\nlag > 50k")

    (post,) = _posts(calls)
    assert post["json"]["spaceId"] == "98304"
    assert post["json"]["parentId"] == "12345"
    assert post["json"]["body"]["representation"] == "storage"
    assert "<h2>Summary</h2>" in post["json"]["body"]["value"]
    assert ack == {
        "space": "SRE",
        "title": "RCA",
        "id": "557057",
        "url": "https://x.atlassian.net/wiki/spaces/SRE/pages/557057/RCA",
        "created_at": "2026-10-01T09:00:00.000Z",
    }


# ---------------------------------------------------------------------------
# Server behaviour
# ---------------------------------------------------------------------------


# Every field the UI's CreatePageResult reads off the ack.
_UI_ACK_FIELDS = {"id", "url", "space", "title", "created_at"}


def _call(server, tool, **args) -> str:
    """Call a tool the way an MCP client would; returns its text."""
    content, _ = asyncio.run(server.call_tool(tool, args))
    return content[0].text


def test_live_tool_returns_the_error_as_data_not_a_crash(monkeypatch, tmp_path):
    from agent.integrations import confluence as cf
    from agent.mcp_servers import confluence as srv

    def boom(*_args, **_kwargs):
        raise IntegrationError("boom", system="confluence", hint="check the token")

    monkeypatch.setattr(srv, "ensure_logs_dir", lambda: tmp_path)
    monkeypatch.setattr(cf, "create_page", boom)

    server = srv.build_server(srv.LiveConfluence())
    out = json.loads(_call(server, "create_page", space="SRE", title="RCA", body="# body"))
    assert (out["error"], out["system"], out["mode"]) == ("boom", "confluence", "live")
    assert "failed: boom" in (tmp_path / "confluence.log").read_text()


def test_live_ack_is_logged_and_carries_the_ui_fields(monkeypatch, tmp_path):
    from agent.mcp_servers import confluence as srv

    _fake_confluence(monkeypatch, dry_run=True)
    monkeypatch.setattr(srv, "ensure_logs_dir", lambda: tmp_path)

    server = srv.build_server(srv.LiveConfluence())
    out = json.loads(_call(server, "create_page", space="SRE", title="RCA", body="# body"))
    assert _UI_ACK_FIELDS <= out.keys()
    assert "Confluence page dry-run" in (tmp_path / "confluence.log").read_text()


def test_stub_files_the_rca_where_live_mode_would(monkeypatch, tmp_path):
    """The knowledge base's real space, under its "Incident reports" page."""
    from agent.mcp_servers import confluence as srv
    from harness.stubs import _kb_pages as kb
    from harness.stubs import confluence_mcp as stub

    monkeypatch.setattr(srv, "ensure_logs_dir", lambda: tmp_path)
    server = stub.build()

    out = json.loads(_call(server, "create_page", space="SRE", title="RCA: lag on cards-prod-euw1", body="# body"))
    assert _UI_ACK_FIELDS <= out.keys()
    assert out["space"] == "DSS26" and out["requested_space"] == "SRE"
    assert out["parent_id"] == kb.INCIDENT_REPORTS_PAGE_ID
    assert out["url"] == (
        f"https://landoop.atlassian.net/wiki/spaces/DSS26/pages/{out['id']}/RCA+lag+on+cards-prod-euw1"
    )
    assert "Confluence page created" in (tmp_path / "confluence.log").read_text()

    # Asking for the right space is not reported as an override.
    again = json.loads(_call(server, "create_page", space="DSS26", title="RCA 2", body="# body"))
    assert "requested_space" not in again
