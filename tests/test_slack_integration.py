"""Tests for the Slack back-end split (fixture vs live).

Slack is the first *write* integration, so these lean on the guardrails
rather than the transport. The property worth protecting is that no code path
reaches ``chat.postMessage`` unless the channel policy allowed it, dry-run is
off, and the message has not already been sent.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from agent.integrations import IntegrationError


@pytest.fixture
def sl(tmp_path, monkeypatch):
    """The live Slack module with a token, no dry run, and a scratch ledger."""
    from agent.integrations import slack as mod

    monkeypatch.setattr(mod, "SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setattr(mod, "SLACK_DRY_RUN", False)
    monkeypatch.setattr(mod, "SLACK_DEFAULT_CHANNEL", "")
    monkeypatch.setattr(mod, "SLACK_CHANNEL_ALLOWLIST", ())
    monkeypatch.setattr(mod, "_LEDGER_PATH", tmp_path / "slack_sent.json")
    return mod


@pytest.fixture
def calls(sl, monkeypatch):
    """Record every Slack API call and return a canned ok response."""
    recorded = []

    def fake_call(method, payload=None):
        recorded.append((method, payload))
        if method == "auth.test":
            return {"ok": True, "user": "sre-bot", "team": "dss26"}
        return {"ok": True, "channel": "C123", "ts": "1700000000.000100"}

    monkeypatch.setattr(sl, "_call", fake_call)
    return recorded


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def test_missing_token_raises_with_the_escape_hatch(monkeypatch):
    from agent.integrations import slack as mod

    monkeypatch.setattr(mod, "SLACK_BOT_TOKEN", "")
    with pytest.raises(IntegrationError) as exc:
        mod._headers()
    assert "SLACK_MODE=stub" in (exc.value.hint or "")


def test_token_is_sent_as_a_bearer(sl):
    assert sl._headers()["Authorization"] == "Bearer xoxb-test"


def test_logical_failure_at_http_200_is_an_error(sl, monkeypatch):
    """Slack answers 200 for missing_scope; only `ok` is a real success signal."""
    class Resp:
        status_code = 200
        headers: dict = {}

        @staticmethod
        def json():
            return {"ok": False, "error": "missing_scope", "needed": "chat:write"}

    class Client:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def post(self, *a, **k): return Resp()

    monkeypatch.setattr(sl.httpx, "Client", Client)
    with pytest.raises(IntegrationError) as exc:
        sl._call("chat.postMessage", {})
    assert "missing_scope" in str(exc.value)
    assert "chat:write" in (exc.value.hint or "")


# ---------------------------------------------------------------------------
# Channel policy
# ---------------------------------------------------------------------------


def test_default_channel_overrides_whatever_the_model_asked_for(sl, calls, monkeypatch):
    """The reporter prompt hardcodes #sre-oncall, which most workspaces lack."""
    monkeypatch.setattr(sl, "SLACK_DEFAULT_CHANNEL", "#sre-sandbox")
    ack = sl.post_message("#sre-oncall", "hello")

    assert calls[-1][1]["channel"] == "sre-sandbox"
    # The redirect must be visible, not silent: an RCA claiming it went to
    # #sre-oncall when it went elsewhere is a lie the reader cannot catch.
    assert ack["requested_channel"] == "sre-oncall"
    assert "overridden" in ack["note"]


def test_allowlist_rejects_an_unlisted_channel(sl, calls, monkeypatch):
    monkeypatch.setattr(sl, "SLACK_CHANNEL_ALLOWLIST", ("sre-sandbox", "#bots"))
    with pytest.raises(IntegrationError) as exc:
        sl.post_message("#general", "hello")
    assert "not in SLACK_CHANNEL_ALLOWLIST" in str(exc.value)
    assert calls == []  # nothing reached the API


def test_allowlist_accepts_a_listed_channel_with_or_without_hash(sl, calls, monkeypatch):
    monkeypatch.setattr(sl, "SLACK_CHANNEL_ALLOWLIST", ("#sre-sandbox",))
    sl.post_message("sre-sandbox", "hello")
    assert calls[-1][1]["channel"] == "sre-sandbox"


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_verifies_the_credential_but_does_not_post(sl, calls, monkeypatch):
    monkeypatch.setattr(sl, "SLACK_DRY_RUN", True)
    ack = sl.post_message("sre-oncall", "hello")

    assert [m for m, _ in calls] == ["auth.test"]  # never chat.postMessage
    assert ack["dry_run"] is True
    assert ack["ts"] is None
    assert ack["authenticated_as"] == "sre-bot"
    assert "SLACK_DRY_RUN=false" in ack["note"]


def test_dry_run_is_the_default_in_live_mode():
    """Going live must be two deliberate steps, not one."""
    import importlib

    import agent.config as cfg

    importlib.reload(cfg)
    assert cfg.SLACK_DRY_RUN is True


def test_dry_run_does_not_consume_the_dedupe_key(sl, calls, monkeypatch):
    """A dry run must not make the real post that follows look like a duplicate."""
    monkeypatch.setattr(sl, "SLACK_DRY_RUN", True)
    sl.post_message("sre-oncall", "hello")

    monkeypatch.setattr(sl, "SLACK_DRY_RUN", False)
    ack = sl.post_message("sre-oncall", "hello")
    assert ack.get("deduplicated") is not True
    assert ack["ts"] == "1700000000.000100"


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


def test_identical_message_is_posted_once(sl, calls):
    """Both the agentic loop and the gateway retry; each retry re-runs the reporter."""
    first = sl.post_message("sre-oncall", "lag 73k on card_auth_event")
    second = sl.post_message("sre-oncall", "lag 73k on card_auth_event")

    assert [m for m, _ in calls] == ["chat.postMessage"]  # exactly one write
    assert first.get("deduplicated") is not True
    assert second["deduplicated"] is True
    assert second["ts"] == first["ts"]  # the original ack is echoed back


def test_different_text_still_posts(sl, calls):
    sl.post_message("sre-oncall", "first incident")
    sl.post_message("sre-oncall", "second incident")
    assert len([m for m, _ in calls if m == "chat.postMessage"]) == 2


def test_same_text_to_a_different_channel_still_posts(sl, calls):
    sl.post_message("sre-oncall", "same text")
    sl.post_message("sre-escalation", "same text")
    assert len([m for m, _ in calls if m == "chat.postMessage"]) == 2


def test_expired_ledger_entries_stop_suppressing(sl, calls, monkeypatch):
    sl.post_message("sre-oncall", "hello")
    monkeypatch.setattr(sl, "SLACK_DEDUPE_TTL_S", 0)
    ack = sl.post_message("sre-oncall", "hello")
    assert ack.get("deduplicated") is not True


def test_a_corrupt_ledger_costs_a_duplicate_not_the_run(sl, calls):
    """Raising here would fail a run; degrading costs at most one extra message."""
    sl._LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    sl._LEDGER_PATH.write_text("{not json", encoding="utf-8")
    ack = sl.post_message("sre-oncall", "hello")
    assert ack["ts"] == "1700000000.000100"


# ---------------------------------------------------------------------------
# The MCP tool
# ---------------------------------------------------------------------------


def _call(server, tool, **args) -> str:
    """Call a tool the way an MCP client would; returns its text."""
    content, _ = asyncio.run(server.call_tool(tool, args))
    return content[0].text


def test_stub_never_touches_the_network(monkeypatch, tmp_path):
    from agent.mcp_servers import slack as srv
    from harness.stubs import slack_mcp as stub

    monkeypatch.setattr(srv, "ensure_logs_dir", lambda: tmp_path)
    ack = json.loads(_call(stub.build(), "post_message", channel="sre-oncall", text="hello"))
    assert ack == {"ok": True, "channel": "sre-oncall", "ts": ack["ts"]}
    assert "(logged)" in (tmp_path / "slack.log").read_text()


def test_live_failure_comes_back_as_data(monkeypatch, tmp_path):
    from agent.integrations import slack as mod
    from agent.mcp_servers import slack as srv

    monkeypatch.setattr(srv, "ensure_logs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        mod, "post_message",
        lambda c, t: (_ for _ in ()).throw(
            IntegrationError("Slack rejected chat.postMessage: channel_not_found",
                             system="slack", hint="check the channel")
        ),
    )
    server = srv.build_server(srv.LiveSlack())
    out = json.loads(_call(server, "post_message", channel="nope", text="hello"))
    assert out["system"] == "slack"
    assert out["mode"] == "live"
    assert "channel_not_found" in out["error"]


@pytest.mark.parametrize(
    "ack,expected",
    [
        ({"ok": True, "ts": "1"}, "posted"),
        ({"ok": True, "dry_run": True}, "dry-run"),
        ({"ok": True, "deduplicated": True}, "deduplicated"),
    ],
)
def test_outcome_label_distinguishes_the_three_successes(ack, expected):
    from agent.mcp_servers import slack as srv

    assert srv.LiveSlack().outcome(ack) == expected


def test_live_tool_description_warns_the_model():
    """A model that thinks it is writing to a log writes a different message."""
    from agent.mcp_servers import slack as srv
    from harness.stubs import slack_mcp as stub

    assert "REAL workspace" in srv.LiveSlack.description
    assert "Dry-run is currently ON" in srv.LiveSlack.description
    assert "REAL" not in stub.LogOnly.description



def test_ledger_path_is_overridable(tmp_path, monkeypatch):
    """Compose points this at the persisted volume; in the image `logs/` is ephemeral."""
    import importlib

    target = tmp_path / "slack_sent.json"
    monkeypatch.setenv("SLACK_LEDGER_PATH", str(target))
    import agent.config as cfg
    importlib.reload(cfg)
    from agent.integrations import slack as mod
    importlib.reload(mod)
    try:
        assert mod._LEDGER_PATH == target
    finally:
        monkeypatch.delenv("SLACK_LEDGER_PATH", raising=False)
        importlib.reload(cfg)
        importlib.reload(mod)


# ---------------------------------------------------------------------------
# Markdown -> Slack mrkdwn
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "markdown, mrkdwn",
    [
        ("**What fired:** lag", "*What fired:* lag"),
        ("[merchant-gateway #10](https://github.com/o/r/pull/10)",
         "<https://github.com/o/r/pull/10|merchant-gateway #10>"),
        # Bold wrapping a code span is still bold; the code is untouched.
        ("**lag on `fraud-decisioning-engine`**", "*lag on `fraud-decisioning-engine`*"),
        ("## Next step", "*Next step*"),
        ("- one\n- two", "• one\n• two"),
        ("revert *#10* first", "revert _#10_ first"),
        # Slack's control characters are escaped, in prose and in code.
        ("double -> string & `a < b`", "double -&gt; string &amp; `a &lt; b`"),
        ("12 * 3 * 4", "12 * 3 * 4"),
    ],
)
def test_markdown_becomes_slack_mrkdwn(markdown, mrkdwn):
    from agent.integrations.slack import markdown_to_mrkdwn

    assert markdown_to_mrkdwn(markdown) == mrkdwn


def test_the_posted_text_is_converted_but_the_dedupe_key_is_not(sl, calls):
    sl.post_message("#sre-oncall", "**Likely cause:** [PR #10](https://github.com/o/r/pull/10)")
    method, payload = calls[-1]
    assert method == "chat.postMessage"
    assert payload["text"] == "*Likely cause:* <https://github.com/o/r/pull/10|PR #10>"
    assert payload["unfurl_links"] is False
    # Posting the same Markdown again is still recognised as a duplicate.
    assert sl.post_message("#sre-oncall", "**Likely cause:** [PR #10](https://github.com/o/r/pull/10)")["deduplicated"]


@pytest.mark.parametrize(
    "configured, asked",
    [("", "#sre-oncall"), ("sre-agent-sandbox", "#sre-agent-sandbox"),
     ("#sre-agent-sandbox", "#sre-agent-sandbox"), ("C0C5MRKEX6K", "C0C5MRKEX6K")],
)
def test_the_reporter_asks_for_the_configured_channel(monkeypatch, configured, asked):
    """Asking for the pinned channel means no redirect for the summary to report."""
    reporter = pytest.importorskip("agent.sub_agents.reporter")
    monkeypatch.setattr(reporter, "SLACK_DEFAULT_CHANNEL", configured)
    assert reporter.slack_channel() == asked


def test_the_ack_names_the_channel_not_just_its_id(sl, calls):
    ack = sl.post_message("#sre-oncall", "hello")
    assert (ack["channel"], ack["channel_id"]) == ("sre-oncall", "C123")
    assert "requested_channel" not in ack
