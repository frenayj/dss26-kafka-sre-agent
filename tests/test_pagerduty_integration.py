"""Tests for PagerDuty in both modes.

Stub mode serves the fixture incidents through our own MCP stub. Live mode
splits in two: the agent server polls the REST API for new incidents (and
must hand the supervisor the same shape a fixture has - the alert payload
folded onto the incident), and the agent talks to PagerDuty's hosted MCP
server, whose writes are narrowed to acknowledge + add_note by
``agent.pagerduty_guard``.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agent.config import resolve_integration_mode
from agent.integrations import IntegrationError

# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------


def test_mode_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("PAGERDUTY_MODE", raising=False)
    assert resolve_integration_mode("pagerduty") == "stub"


@pytest.mark.parametrize("raw", ["live", "LIVE", " live "])
def test_mode_accepts_live(monkeypatch, raw):
    monkeypatch.setenv("PAGERDUTY_MODE", raw)
    assert resolve_integration_mode("pagerduty") == "live"


@pytest.mark.parametrize("raw", ["", "prod", "real", "1"])
def test_unknown_mode_falls_back_to_stub(monkeypatch, raw):
    """A typo must degrade to the offline back-end, not crash the process."""
    monkeypatch.setenv("PAGERDUTY_MODE", raw)
    assert resolve_integration_mode("pagerduty") == "stub"


# ---------------------------------------------------------------------------
# Live back-end: credential handling
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_with_a_hint(monkeypatch):
    from agent.integrations import pagerduty as pd

    monkeypatch.setattr(pd, "PAGERDUTY_API_KEY", "")
    with pytest.raises(IntegrationError) as exc:
        pd._headers()
    assert exc.value.system == "pagerduty"
    assert "PAGERDUTY_API_KEY" in str(exc.value)
    # The hint has to name the escape hatch, or the operator's next move is a
    # search through source rather than a one-line env change.
    assert "PAGERDUTY_MODE=stub" in (exc.value.hint or "")


def test_api_key_is_sent_as_a_pd_token_header(monkeypatch):
    from agent.integrations import pagerduty as pd

    monkeypatch.setattr(pd, "PAGERDUTY_API_KEY", "abc123")
    headers = pd._headers()
    assert headers["Authorization"] == "Token token=abc123"
    # PD serves an older response shape without the versioning Accept header.
    assert headers["Accept"] == "application/vnd.pagerduty+json;version=2"


# ---------------------------------------------------------------------------
# Live back-end: wire shape -> contract shape
# ---------------------------------------------------------------------------


_PD_INCIDENT = {
    "id": "Q1ABCDEF",
    "type": "incident",
    "incident_number": 48217,
    "title": "[Datadog] kafka_consumer_lag CRITICAL - fraud-decisioning-engine",
    "status": "triggered",
    "created_at": "2026-09-21T09:14:02Z",
    "urgency": "high",
    "priority": {"id": "P53ZZH5", "summary": "P1", "name": "P1"},
    "service": {"id": "PSVC42A", "summary": "fraud-decisioning-svc",
                "name": "fraud-decisioning-svc"},
}

# A real Datadog->PD alert: the monitoring payload lives HERE, not on the
# incident. This is the whole reason `_fold_alert_details` exists.
_PD_ALERT = {
    "id": "PALERT1",
    "summary": "kafka_consumer_lag CRITICAL",
    "status": "triggered",
    "severity": "critical",
    "created_at": "2026-09-21T09:14:02Z",
    "integration": {"summary": "Datadog"},
    "body": {
        "contexts": [{"type": "link", "href": "https://dd/monitors/19283746"}],
        "details": {
            "monitor_name": "kafka_consumer_lag",
            "monitor_query": (
                "avg(last_5m):avg:kafka.consumer_lag{"
                "kafka_cluster:cards-prod-euw1,"
                "consumer_group:fraud-decisioning-engine} > 50000"
            ),
            "metric_value": 73412,
            "tags": ["kafka_cluster:cards-prod-euw1", "env:prod"],
        },
    },
}


def _stub_get(monkeypatch, responses):
    """Replace the module's HTTP layer with a path -> payload lookup."""
    from agent.integrations import pagerduty as pd

    def fake_get(path, params=None):
        if path not in responses:
            raise IntegrationError(f"unexpected path {path}", system="pagerduty")
        return responses[path]

    monkeypatch.setattr(pd, "_get", fake_get)
    return pd


def test_get_incident_folds_alert_details_onto_the_incident(monkeypatch):
    pd = _stub_get(monkeypatch, {
        "/incidents/Q1ABCDEF": {"incident": dict(_PD_INCIDENT)},
        "/incidents/Q1ABCDEF/alerts": {"alerts": [_PD_ALERT]},
    })

    payload = pd.get_incident("Q1ABCDEF")
    inc = payload["incident"]

    # Without this fold, triage receives an incident with no monitor query,
    # no tags and no metric value - i.e. nothing to triage.
    assert inc["custom_details"]["monitor_query"].startswith("avg(last_5m)")
    assert inc["custom_details"]["metric_value"] == 73412
    assert inc["alert_contexts"][0]["href"] == "https://dd/monitors/19283746"
    assert inc["alerts"][0]["integration"] == "Datadog"


def test_existing_custom_details_are_not_overwritten(monkeypatch):
    incident = dict(_PD_INCIDENT, custom_details={"source": "webhook"})
    pd = _stub_get(monkeypatch, {
        "/incidents/Q1ABCDEF": {"incident": incident},
        "/incidents/Q1ABCDEF/alerts": {"alerts": [_PD_ALERT]},
    })
    inc = pd.get_incident("Q1ABCDEF")["incident"]
    assert inc["custom_details"] == {"source": "webhook"}


def test_unreadable_alerts_still_yield_an_incident(monkeypatch):
    """Losing the monitor payload thins the answer; losing the incident ends the run."""
    from agent.integrations import pagerduty as pd

    def fake_get(path, params=None):
        if path.endswith("/alerts"):
            raise IntegrationError("429", system="pagerduty")
        return {"incident": dict(_PD_INCIDENT)}

    monkeypatch.setattr(pd, "_get", fake_get)
    inc = pd.get_incident("Q1ABCDEF")["incident"]
    assert inc["id"] == "Q1ABCDEF"
    assert "custom_details" not in inc


def test_list_incidents_normalises_bare_objects_to_the_envelope(monkeypatch):
    """PD's list endpoint omits the envelope its show endpoint uses."""
    pd = _stub_get(monkeypatch, {
        "/incidents": {"incidents": [dict(_PD_INCIDENT)]},
    })
    out = pd.list_incidents(limit=5)
    assert out == [{"incident": _PD_INCIDENT}]


def test_list_incidents_rejects_a_malformed_body(monkeypatch):
    pd = _stub_get(monkeypatch, {"/incidents": {"not_incidents": []}})
    with pytest.raises(IntegrationError):
        pd.list_incidents()


# ---------------------------------------------------------------------------
# Cross-mode: the inbox projection must not depend on the back-end
# ---------------------------------------------------------------------------


def test_stub_serves_the_fixture_incidents():
    pytest.importorskip("mcp.server.fastmcp")
    from harness.stubs import pagerduty_mcp as srv

    out = json.loads(srv.get_incident("PI7K3FQ"))
    assert out["incident"]["id"] == "PI7K3FQ"
    assert out["incident"]["custom_details"]["monitor_name"] == "kafka_consumer_lag"

    rows = json.loads(srv.list_recent_incidents(10))
    assert [r["id"] for r in rows] == ["PI7K3FQ"]


# ---------------------------------------------------------------------------
# Live mode: write policy on PagerDuty's hosted MCP
# ---------------------------------------------------------------------------


def _guard():
    pytest.importorskip("strands")
    from agent import pagerduty_guard

    return pagerduty_guard


_ACK = {"action": "update", "manage_request": {"incident_ids": ["Q1"], "status": "acknowledged"}}


@pytest.mark.parametrize(
    "request_",
    [_ACK, {"action": "add_note", "incident_id": "Q1", "note": "investigating"}],
)
def test_policy_allows_acknowledge_and_notes(request_):
    assert _guard().blocked_reason({"request": request_}) is None


@pytest.mark.parametrize(
    "request_",
    [
        {"action": "update", "manage_request": {"incident_ids": ["Q1"], "status": "resolved"}},
        {"action": "update", "manage_request": {"incident_ids": ["Q1"], "urgency": "low"}},
        {
            "action": "update",
            "manage_request": {"incident_ids": ["Q1"], "status": "acknowledged", "escalation_level": 2},
        },
        {
            "action": "update",
            "manage_request": {"incident_ids": ["Q1"], "status": "acknowledged", "assignment": {"id": "PUSER"}},
        },
        {"action": "create", "incident": {"title": "x", "service": {"id": "PSVC"}}},
        {"action": "add_responders", "incident_id": "Q1", "request": {}},
        {"action": "start_workflow", "workflow_id": "PWF"},
        {},
    ],
)
def test_policy_blocks_every_other_write(request_):
    assert _guard().blocked_reason({"request": request_})


def test_policy_reads_json_encoded_requests():
    """Models sometimes send the nested request as a string - judge it all the same."""
    guard = _guard()
    assert guard.blocked_reason(json.dumps({"request": _ACK})) is None
    assert guard.blocked_reason({"request": json.dumps(_ACK)}) is None
    resolve = {**_ACK, "manage_request": {"incident_ids": ["Q1"], "status": "resolved"}}
    assert guard.blocked_reason({"request": json.dumps(resolve)})


def test_policy_cancels_only_refused_writes():
    guard = _guard()
    policy = guard.PagerDutyWritePolicy()

    create = SimpleNamespace(
        tool_use={"name": "manage_incidents", "input": {"request": {"action": "create"}}},
        cancel_tool=False,
    )
    policy._check(create)
    # The UI keys its "Blocked" badge on this prefix.
    assert create.cancel_tool.startswith("Blocked by the demo's PagerDuty policy")

    ack = SimpleNamespace(
        tool_use={"name": "manage_incidents", "input": {"request": _ACK}}, cancel_tool=False
    )
    policy._check(ack)
    assert ack.cancel_tool is False

    read = SimpleNamespace(
        tool_use={"name": "browse_incidents", "input": {"request": {"action": "list"}}},
        cancel_tool=False,
    )
    policy._check(read)
    assert read.cancel_tool is False


# ---------------------------------------------------------------------------
# Live mode: the agent server's incident poller and claim endpoint
# ---------------------------------------------------------------------------


def _server():
    pytest.importorskip("fastapi")
    pytest.importorskip("strands")
    from agent import server

    return server


class _StopPolling(Exception):
    pass


def _poll_once(monkeypatch, server, incidents):
    async def stop(_seconds):
        raise _StopPolling

    monkeypatch.setattr(server.asyncio, "sleep", stop)
    with pytest.raises(_StopPolling):
        asyncio.run(server._poll_pagerduty(incidents))


def test_poller_queues_new_incidents_and_flags_triggered_ones(monkeypatch):
    server = _server()
    from agent.integrations import pagerduty as pd

    acked = {**_PD_INCIDENT, "id": "Q2ACKED", "status": "acknowledged"}
    by_id = {_PD_INCIDENT["id"]: _PD_INCIDENT, acked["id"]: acked}
    monkeypatch.setattr(
        pd, "list_incidents", lambda limit: [{"incident": i} for i in by_id.values()]
    )
    monkeypatch.setattr(
        pd, "get_incident",
        lambda incident_id: {"incident": {**by_id[incident_id], "custom_details": {"tags": []}}},
    )
    incidents = {
        "QGONE": {"id": "QGONE", "status": "completed"},
        "QRUNNING": {"id": "QRUNNING", "status": "in_progress"},
    }

    _poll_once(monkeypatch, server, incidents)

    new = incidents["Q1ABCDEF"]
    assert new["auto_run"] is True
    assert new["severity"] == "P1"
    # The full payload (with the folded alert details) is what /run hands the
    # supervisor, so it must come from get_incident, not the list row.
    assert new["payload"]["incident"]["custom_details"] == {"tags": []}
    # Already acknowledged = someone is on it: queue it, don't auto-run it.
    assert incidents["Q2ACKED"]["auto_run"] is False
    # Resolved in PagerDuty -> out of the queue, unless a run is mid-flight.
    assert "QGONE" not in incidents
    assert "QRUNNING" in incidents


def test_poller_survives_a_pagerduty_outage(monkeypatch):
    server = _server()
    from agent.integrations import pagerduty as pd

    def down(limit):
        raise IntegrationError("unreachable", system="pagerduty")

    monkeypatch.setattr(pd, "list_incidents", down)
    incidents = {"QKEPT": {"id": "QKEPT", "status": "completed"}}

    _poll_once(monkeypatch, server, incidents)  # reaches sleep -> loop survives

    # A failed poll says nothing about what is open - keep the queue as is.
    assert "QKEPT" in incidents


def test_claim_hands_an_incident_to_exactly_one_dashboard(monkeypatch):
    server = _server()
    monkeypatch.setitem(server._state, "incidents", {"Q1": {"id": "Q1", "auto_run": True}})

    first = asyncio.run(server.claim_incident("Q1"))
    second = asyncio.run(server.claim_incident("Q1"))
    missing = asyncio.run(server.claim_incident("QNOPE"))

    assert first == {"claimed": "Q1"}
    assert second.status_code == 409
    assert missing.status_code == 404
