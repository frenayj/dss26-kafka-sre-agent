"""``GET /runs/:id/events`` follows a run that is still executing.

A dashboard that opens a run from history while another dashboard drives it
must keep receiving frames until the run ends - not stop at whatever was
stored when it connected. A finished run (or a stale 'running' row left by a
restart) replays once and closes.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Tuple

import httpx

from agent import server
from agent.run_store import RunStore


def _frames(body: str) -> List[Tuple[str, Dict[str, Any]]]:
    out = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def _new_run(store: RunStore) -> str:
    run_id = store.create_run(preset="full", incident_id="INC-1", prompt="p")
    store.append_event(run_id, seq=0, kind="start", source=None, payload={})
    store.append_event(
        run_id, seq=1, kind="text", source="supervisor", payload={"delta": "early"}
    )
    return run_id


async def _get_events(run_id: str) -> List[Tuple[str, Dict[str, Any]]]:
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    return _frames(resp.text)


def test_finished_run_replays_and_closes(tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs.db")
    monkeypatch.setitem(server._state, "store", store)
    run_id = _new_run(store)  # row stays 'running', but nothing executes it

    frames = asyncio.run(_get_events(run_id))

    assert [k for k, _ in frames] == ["start", "text", "done"]
    assert frames[0][1]["following"] is False


def test_active_run_is_followed_until_it_ends(tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs.db")
    monkeypatch.setitem(server._state, "store", store)
    run_id = _new_run(store)
    monkeypatch.setattr(server, "_active_runs", {run_id: None})

    async def drive_rest_of_run() -> None:
        # Lands after the follower has drained the stored frames.
        await asyncio.sleep(server._FOLLOW_POLL_S * 3)
        store.append_event(
            run_id, seq=2, kind="text", source="supervisor", payload={"delta": "late"}
        )
        store.append_event(run_id, seq=3, kind="done", source=None, payload={})
        store.finish_run(run_id, status="done")
        server._active_runs.pop(run_id)

    async def scenario():
        driver = asyncio.create_task(drive_rest_of_run())
        frames = await _get_events(run_id)
        await driver
        return frames

    frames = asyncio.run(scenario())

    assert frames[0][1]["following"] is True
    deltas = [d.get("delta") for k, d in frames if k == "text"]
    assert deltas == ["early", "late"]
    assert frames[-1][0] == "done"
