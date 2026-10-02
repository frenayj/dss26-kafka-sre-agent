"""A run executes on the server, independently of the browser that started it.

Reloading the dashboard, switching to another page or losing the connection
used to cancel the agent mid-run, because the run lived inside its SSE
response. Now ``POST /runs`` starts it as a task and ``GET /runs/{id}/events``
only follows the stored frames.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Tuple

import httpx
import pytest

from agent import server
from agent.run_store import RunStore

INCIDENT = {"id": "INC-1", "payload": {"incident": {"id": "INC-1"}}, "title": "lag", "status": "pending"}


class FakeModel:
    def get_config(self) -> dict:
        return {"model_id": "claude"}


class FakeSupervisor:
    """Streams a few text deltas, pausing between them like a model would."""

    system_prompt = "You are the incident commander."
    tool_names = ["triage_agent"]
    model = FakeModel()

    def __init__(self, deltas: List[str], pause: float = 0.05):
        self.deltas, self.pause = deltas, pause

    async def stream_async(self, prompt: str):
        for delta in self.deltas:
            await asyncio.sleep(self.pause)
            yield {"data": delta}


@pytest.fixture
def agent(tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs.db")
    supervisor = FakeSupervisor(["one ", "two ", "three"])
    monkeypatch.setitem(server._state, "store", store)
    monkeypatch.setitem(server._state, "incidents", {"INC-1": dict(INCIDENT)})
    monkeypatch.setitem(server._state, "make_supervisor", lambda *a, **k: supervisor)
    monkeypatch.setattr(server, "_active_runs", {})
    monkeypatch.setattr(server.tracing, "flush", lambda: None)
    # Each test starts from the *_MODEL defaults.
    monkeypatch.delitem(server._state, "models", raising=False)
    return store, supervisor


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t")


def _frames(body: str) -> List[Tuple[str, Dict[str, Any]]]:
    out = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((fields["event"], json.loads(fields["data"])))
    return out


async def _wait_until_finished(run_id: str) -> None:
    for _ in range(200):
        if run_id not in server._active_runs:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("run did not finish")


def _start_frame_models(client: httpx.AsyncClient, body: Dict[str, Any]):
    async def go():
        run_id = (await client.post("/runs", json=body)).json()["run_id"]
        await _wait_until_finished(run_id)
        return _frames((await client.get(f"/runs/{run_id}/events")).text)[0][1]["models"]

    return go()


def test_a_run_uses_the_models_set_on_the_server(agent):
    """The operator console and every dashboard share one model setting."""

    async def scenario():
        async with _client() as client:
            before = (await client.get("/models")).json()["models"]
            changed = await client.patch("/models", json={"triage": "claude-haiku"})
            used = await _start_frame_models(client, {"incident_id": "INC-1"})
            after = (await client.get("/models")).json()["models"]
        return before, changed, used, after

    before, changed, used, after = asyncio.run(scenario())
    assert set(before) == {"supervisor", "triage", "diagnosis", "forensics", "reporter"}
    assert before["triage"] == "claude"
    assert changed.status_code == 200 and changed.json()["models"]["triage"] == "claude-haiku"
    assert used == {**before, "triage": "claude-haiku"}
    assert after == used


def test_a_run_can_still_name_its_own_models(agent):
    async def scenario():
        async with _client() as client:
            await client.patch("/models", json={"triage": "claude-haiku"})
            return await _start_frame_models(
                client, {"incident_id": "INC-1", "models": {"reporter": "claude-haiku", "triage": "claude"}}
            )

    used = asyncio.run(scenario())
    assert used["reporter"] == "claude-haiku" and used["triage"] == "claude"


def test_the_model_setting_only_takes_gateway_aliases_and_known_roles(agent):
    async def scenario():
        async with _client() as client:
            alias = await client.patch("/models", json={"triage": "claude-haiku-4-5-20251001"})
            role = await client.patch("/models", json={"pilot": "claude"})
            # A bad entry rejects the whole change.
            mixed = await client.patch("/models", json={"reporter": "claude-haiku", "triage": "nope"})
            return alias, role, mixed, (await client.get("/models")).json()["models"]

    alias, role, mixed, models = asyncio.run(scenario())
    assert alias.status_code == role.status_code == mixed.status_code == 400
    assert "not a gateway alias" in alias.json()["error"]
    assert set(models.values()) == {"claude"}


def test_a_default_the_gateway_does_not_know_falls_back_to_claude(agent, monkeypatch):
    monkeypatch.setitem(server._ROLE_DEFAULTS, "supervisor", "claude-haiku-4-5-20251001")
    monkeypatch.setitem(server._ROLE_DEFAULTS, "triage", "claude-haiku")

    async def scenario():
        async with _client() as client:
            return (await client.get("/models")).json()["models"]

    models = asyncio.run(scenario())
    assert models["supervisor"] == "claude" and models["triage"] == "claude-haiku"


def test_a_run_completes_with_nobody_watching(agent):
    store, _ = agent

    async def scenario():
        async with _client() as client:
            resp = await client.post("/runs", json={"incident_id": "INC-1", "models": {"triage": "claude-haiku"}})
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]
            await _wait_until_finished(run_id)  # no stream was ever opened
            events = (await client.get(f"/runs/{run_id}/events")).text
        return run_id, events

    run_id, events = asyncio.run(scenario())
    assert store.get_run(run_id)["status"] == "done"
    frames = _frames(events)
    # The dashboard prices each agent with the model the run used.
    assert frames[0][0] == "start"
    assert frames[0][1]["models"]["triage"] == "claude-haiku"
    # Then what the supervisor starts from: the incident prompt and its setup.
    kind, handoff = frames[1]
    assert kind == "handoff" and handoff["source"] == "supervisor"
    assert handoff["callId"] is None and "INC-1" in handoff["prompt"]
    assert handoff["systemPrompt"] == "You are the incident commander."
    assert handoff["tools"] == ["triage_agent"] and handoff["model"] == "claude"
    assert "".join(d["delta"] for k, d in frames if k == "text") == "one two three"
    assert frames[-1] == ("done", {"status": "done", "at": frames[-1][1]["at"]})
    assert server._state["incidents"]["INC-1"]["status"] == "completed"


def test_cancel_stops_the_run_and_says_so(agent):
    store, supervisor = agent
    supervisor.pause = 0.5

    async def scenario():
        async with _client() as client:
            run_id = (await client.post("/runs", json={"incident_id": "INC-1"})).json()["run_id"]
            await asyncio.sleep(0.1)
            assert (await client.post(f"/runs/{run_id}/cancel")).status_code == 200
            await _wait_until_finished(run_id)
            assert (await client.post(f"/runs/{run_id}/cancel")).status_code == 409
            return run_id, (await client.get(f"/runs/{run_id}/events")).text

    run_id, events = asyncio.run(scenario())
    assert store.get_run(run_id)["status"] == "cancelled"
    assert ("agent_error", "Cancelled") in [(k, d.get("type")) for k, d in _frames(events)]


def test_a_reconnect_resumes_after_the_last_frame(agent):
    _, supervisor = agent

    async def scenario():
        async with _client() as client:
            run_id = (await client.post("/runs", json={"incident_id": "INC-1"})).json()["run_id"]
            await _wait_until_finished(run_id)
            # As an EventSource does after a dropped connection.
            resp = await client.get(f"/runs/{run_id}/events", headers={"Last-Event-ID": "2"})
            return resp.text

    frames = _frames(asyncio.run(scenario()))
    # seq 0 is the stored start frame, seq 1 the supervisor's handoff, seq 2
    # the first delta: all already seen.
    assert [d["delta"] for k, d in frames if k == "text"] == ["two ", "three"]
    assert frames[0][0] != "start"


def test_unknown_incident_is_404(agent):
    async def scenario():
        async with _client() as client:
            return await client.post("/runs", json={"incident_id": "nope"})

    assert asyncio.run(scenario()).status_code == 404
