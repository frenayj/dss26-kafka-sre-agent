"""FastAPI server: live timeline view of the Kafka SRE supervisor.

The Python supervisor's MCP clients are opened once at startup (held open
for the whole server lifetime via ``ExitStack`` inside the ASGI lifespan),
and the React UI lives in ``ui/``.

A run executes on the server, independently of any browser:
``POST /runs`` starts it as a background task, which translates each Strands
event into a named frame (``text``, ``reasoning``, ``tool``, ``tool_result``,
``handoff``, ``assistant_done``, ``done``, ``agent_error``) and stores it in
``logs/runs.db`` via ``agent.run_store.RunStore``. ``GET /runs/{id}/events``
streams those frames as SSE - following the run while it executes, or
replaying it once it has ended - so a reload, a closed tab or a second
dashboard never affects the run itself. ``POST /runs/{id}/cancel`` stops it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from agent import tracing
from agent.config import (
    DIAGNOSIS_MODEL,
    FORENSICS_MODEL,
    PAGERDUTY_MODE,
    PAGERDUTY_POLL_S,
    REPORTER_MODEL,
    SUPERVISOR_MODEL,
    TRIAGE_MODEL,
    resolve_model,
)
from agent.mcp_registry import list_mcp_servers
from agent.models import gateway_models
from agent.run_store import RunStore, now_ms
from agent.runner import build_supervisor_in_stack
from agent.skills_registry import list_available_skills
from agent.sub_agents.supervisor import agent_context, current_event_queue

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "logs" / "runs.db"

# Each "preset" the dashboard offers maps to a different framing of the user's
# request to the supervisor. The incident payload (when present) is appended
# below the framing, mirroring what `runner.run()` feeds the CLI path.
PRESET_PROMPTS: Dict[str, str] = {
    "full": (
        "Run the full SRE incident-response workflow end-to-end on the loaded "
        "payload: triage the incident, diagnose the Kafka clusters with Lenses, "
        "find the offending merged PR, then write the Confluence RCA and post "
        "the Slack summary."
    ),
    "triage": (
        "Run the triage sub-agent on the loaded payload and return the "
        "structured triage summary. Do not move on to diagnosis or forensics."
    ),
    "diagnose": (
        "Using the loaded incident as context, run the Kafka diagnosis "
        "sub-agent against the affected cluster and consumer group. Return "
        "the structured diagnosis and root-cause hypothesis."
    ),
    "forensics": (
        "Search recent merged PRs for the service mentioned in the loaded "
        "incident and identify the most likely offending change. Return the "
        "PR number, title, author and the relevant snippet."
    ),
}


_state: Dict[str, Any] = {}

# Runs executing in this process right now, with their tasks. The runs
# table's ``status`` can't answer that alone: a server restart mid-run leaves
# the row at 'running' forever. /runs/:id/events follows only these.
_active_runs: dict[str, Optional[asyncio.Task]] = {}

# How often a follower of a run in progress checks the store for new frames.
_FOLLOW_POLL_S = 0.1


# Fields the incident-list UI renders per row (the full payload is omitted).
_INCIDENT_SUMMARY_FIELDS = (
    "id",
    "created_at",
    "title",
    "severity",
    "service",
    "status",
    "last_run_id",
    "auto_run",
)


def _build_incident_row(
    payload: Dict[str, Any], *, auto_run: bool = False
) -> Dict[str, Any]:
    """Turn a PagerDuty-shaped payload into an in-memory incident row.

    ``auto_run`` asks the dashboard to start a run on its own - set for live
    PagerDuty incidents that arrive still ``triggered`` (see the poller).
    """
    inc = payload.get("incident") or payload
    return {
        "id": inc.get("id"),
        "payload": payload,
        "title": inc.get("title") or inc.get("summary"),
        "severity": (inc.get("priority") or {}).get("name"),
        "service": (inc.get("service") or {}).get("name")
        or (inc.get("service") or {}).get("summary"),
        "status": "pending",
        "last_run_id": None,
        "auto_run": auto_run,
        "created_at": now_ms(),
    }


def _incident_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: row.get(k) for k in _INCIDENT_SUMMARY_FIELDS}


def _set_incident_status(
    incident_id: str, status: str, run_id: Optional[str] = None
) -> None:
    """Update an in-memory incident's status / last_run_id (best-effort)."""
    row = (_state.get("incidents") or {}).get(incident_id)
    if row is not None:
        row["status"] = status
        if run_id is not None:
            row["last_run_id"] = run_id


async def _poll_pagerduty(incidents: Dict[str, Dict[str, Any]]) -> None:
    """Mirror PagerDuty's open incidents into the dashboard queue (live mode).

    Polling rather than a webhook: it needs no inbound route to this machine,
    so it works on any network without a tunnel, at the cost of a few
    seconds of lag.

    An incident that arrives still ``triggered`` is flagged ``auto_run``: one
    dashboard claims it (``POST /incidents/{id}/claim``) and starts the run,
    whose first act is to acknowledge it - so a server restart does not run
    the same page twice. Incidents resolved in PagerDuty leave the queue,
    unless a run on them is in progress.
    """
    from agent.integrations import IntegrationError
    from agent.integrations import pagerduty as pd

    while True:
        try:
            listed = await asyncio.to_thread(pd.list_incidents, 25)
            open_ids = set()
            for envelope in listed:
                inc = envelope["incident"]
                incident_id = inc.get("id")
                if not incident_id:
                    continue
                open_ids.add(incident_id)
                if incident_id in incidents:
                    continue
                # The list endpoint carries no alert payload; get_incident
                # folds the monitor's tags onto the incident like the stub has.
                full = await asyncio.to_thread(pd.get_incident, incident_id)
                incidents[incident_id] = _build_incident_row(
                    full, auto_run=inc.get("status") == "triggered"
                )
                logger.info("PagerDuty incident %s queued", incident_id)
            for incident_id in [
                i
                for i, row in incidents.items()
                if i not in open_ids and row.get("status") != "in_progress"
            ]:
                del incidents[incident_id]
        except IntegrationError as exc:
            logger.warning("PagerDuty poll failed: %s", exc)
        except Exception:  # noqa: BLE001 - a poll bug must not kill the loop
            logger.exception("PagerDuty poll crashed")
        await asyncio.sleep(PAGERDUTY_POLL_S)


def _stub_incidents(client: Any) -> List[Dict[str, Any]]:
    """Every incident the PagerDuty stub serves, read through its MCP tools.

    The agent asks the stub the way triage does, so it never needs to know
    where the stub's incidents come from.
    """

    def call(tool: str, args: Dict[str, Any]) -> Any:
        result = client.call_tool_sync(f"queue-{tool}", tool, args)
        text = "".join(c.get("text", "") for c in result.get("content") or [])
        return json.loads(text)

    try:
        rows = call("list_recent_incidents", {"limit": 25})
        return [call("get_incident", {"incident_id": row["id"]}) for row in rows]
    except Exception:  # noqa: BLE001 - an empty queue beats a server that won't start
        logger.exception("could not read the PagerDuty stub's incidents")
        return []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Spawn MCP clients once; tear them down on shutdown.

    Run history persists to ``logs/runs.db`` via ``RunStore``
    (``AGENT_DB_PATH`` overrides it; the container keeps it on a volume).
    The incident queue is held in memory: polled from PagerDuty when it is
    live, read once from the PagerDuty stub otherwise.
    """
    # Traces go to Phoenix. Opens no connection here; an unreachable
    # collector only costs traces (see agent/tracing.py).
    tracing.init_tracer_provider()

    db_path = Path(os.getenv("AGENT_DB_PATH", str(DEFAULT_DB_PATH)))
    store = RunStore(db_path)

    # Live PagerDuty starts empty and fills from the poller. In stub mode the
    # queue is whatever the PagerDuty stub serves - the same incidents triage
    # will fetch. Status / last_run_id are tracked in memory across runs.
    incidents: Dict[str, Dict[str, Any]] = {}
    live = PAGERDUTY_MODE == "live"

    _state["store"] = store
    _state["incidents"] = incidents
    with ExitStack() as stack:
        make_supervisor, info, clients = build_supervisor_in_stack(stack)
        if not live:
            for payload in _stub_incidents(clients["pagerduty"]):
                row = _build_incident_row(payload)
                incidents[row["id"]] = row
        _state["make_supervisor"] = make_supervisor
        _state["info"] = info
        poller = (
            asyncio.create_task(_poll_pagerduty(incidents))
            if live and PAGERDUTY_POLL_S > 0
            else None
        )
        try:
            yield
        finally:
            if poller is not None:
                poller.cancel()
            # Stop in-flight runs so each closes its row before the store does.
            runs = [t for t in _active_runs.values() if t is not None]
            for task in runs:
                task.cancel()
            await asyncio.gather(*runs, return_exceptions=True)
            store.close()
            _state.clear()


# FastAPI's own telemetry is off. Left on, it installs a bare tracer provider
# at startup (OTEL_EXPORTER_OTLP_ENDPOINT is set), before the lifespan runs
# tracing.init_tracer_provider(). Ours is then refused, and spans reach
# Phoenix without the OpenInference translation or the run ids, in the
# default project, alongside an HTTP span for every dashboard poll.
app = FastAPI(
    title="Kafka SRE Agent (live view)",
    lifespan=lifespan,
    telemetry={"auto_configure": False, "tracing": False, "metrics": False, "logs": False},
)

# The browser UI runs on a different origin than the agent - the Vite dev
# server on :5173, or the containerized nginx build on :8080 - so allow both
# to fetch /run (SSE), /presets, /ping, /runs. Override the list via
# AGENT_CORS_ORIGINS (comma-separated) for other deployments.
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8080,http://127.0.0.1:8080"
)
_cors_origins = [
    o.strip()
    for o in os.getenv("AGENT_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# ---- helpers ---------------------------------------------------------------


def _sse(event: str, data: Any, event_id: Optional[int] = None) -> str:
    """Format a single SSE frame. Accepts a dict (json-encoded) or a string."""
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {payload}\n\n"


def _build_prompt(preset: str, payload: str) -> str:
    """Compose the supervisor's user prompt from a preset framing + the
    incident payload (JSON string from the incidents store)."""
    framing = PRESET_PROMPTS.get(preset, PRESET_PROMPTS["full"])
    if not payload:
        return framing
    return (
        "A new PagerDuty incident has fired. The incident payload is below.\n\n"
        "----- INCIDENT PAYLOAD -----\n"
        f"{payload}\n"
        "----- END INCIDENT PAYLOAD -----\n\n"
        f"Request: {framing}"
    )


# ---- routes ----------------------------------------------------------------


@app.get("/ping")
async def ping() -> Dict[str, Any]:
    return {"status": "healthy", "tools": _state.get("info", {})}


@app.get("/presets")
async def list_presets() -> Dict[str, Any]:
    return {"presets": dict(PRESET_PROMPTS)}


# ---- incidents (demo set in stub mode, polled from PagerDuty when live) ----

@app.get("/incidents")
async def list_incidents(limit: int = 100) -> Dict[str, Any]:
    incidents: Optional[Dict[str, Any]] = _state.get("incidents")
    if incidents is None:
        return JSONResponse({"error": "incidents not ready"}, status_code=503)
    limit = max(1, min(500, limit))
    rows = list(incidents.values())[:limit]
    return {"incidents": [_incident_summary(r) for r in rows]}


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    incidents: Optional[Dict[str, Any]] = _state.get("incidents")
    if incidents is None:
        return JSONResponse({"error": "incidents not ready"}, status_code=503)
    row = incidents.get(incident_id)
    if row is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return row


@app.post("/incidents/{incident_id}/claim")
async def claim_incident(incident_id: str):
    """Hand an ``auto_run`` incident to exactly one dashboard.

    Every open dashboard sees the flag on its next poll. The first to claim
    starts the run and the rest get 409, so two browser tabs never work the
    same page twice (two acknowledgements, two RCAs).
    """
    row = (_state.get("incidents") or {}).get(incident_id)
    if row is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    if not row.get("auto_run"):
        return JSONResponse({"error": "already claimed"}, status_code=409)
    row["auto_run"] = False
    return {"claimed": incident_id}


# The gateway alias each agent role runs on: one setting for the whole server,
# so every open dashboard and the operator console show and change the same
# thing, and a run started by a PagerDuty page uses it too. It lives in
# memory; a restart goes back to the *_MODEL defaults.
_ROLE_DEFAULTS: Dict[str, str] = {
    "supervisor": SUPERVISOR_MODEL,
    "triage": TRIAGE_MODEL,
    "diagnosis": DIAGNOSIS_MODEL,
    "forensics": FORENSICS_MODEL,
    "reporter": REPORTER_MODEL,
}
_FALLBACK_MODEL = "claude"


def _unknown_alias(alias: str) -> bool:
    """True when litellm.yaml doesn't define ``alias`` (never, if it can't be read)."""
    known = gateway_models()
    return bool(known) and alias not in known


def _run_models() -> Dict[str, str]:
    models = _state.get("models")
    if models is None:
        models = {}
        for role, alias in _ROLE_DEFAULTS.items():
            if _unknown_alias(alias):
                logger.warning(
                    "%s_MODEL=%s is not a gateway alias (agent/gateway/litellm.yaml); using %s",
                    role.upper(), alias, _FALLBACK_MODEL,
                )
                alias = _FALLBACK_MODEL
            models[role] = alias
        _state["models"] = models
    return models


@app.get("/models")
async def get_models() -> Dict[str, Any]:
    """The alias each agent role runs on in the next run."""
    return {"models": _run_models()}


@app.patch("/models")
async def update_models(patch: Dict[str, str]):
    """Point one or more roles at another gateway alias, from the next run on."""
    for role, alias in patch.items():
        if role not in _ROLE_DEFAULTS:
            return JSONResponse({"error": f"unknown role {role!r}"}, status_code=400)
        if _unknown_alias(alias):
            return JSONResponse({"error": f"{alias!r} is not a gateway alias"}, status_code=400)
    models = _run_models()
    models.update(patch)
    return {"models": models}


@app.get("/skills")
async def list_skills() -> Dict[str, Any]:
    """Available Kafka skills the diagnosis sub-agent can activate.

    The toggle UI in the sidebar pulls from this list and passes its
    selection back as the ``skills=`` query param on ``/run``.
    """
    return {"skills": [s.as_dict() for s in list_available_skills()]}


@app.get("/mcp_servers")
async def list_mcp() -> Dict[str, Any]:
    """Available MCP servers, with which sub-agent consumes each.

    Tool counts come from the supervisor's startup discovery (see
    ``runner.build_supervisor_in_stack``); if the agent isn't up yet they
    fall back to 0.
    """
    info: Dict[str, Any] = _state.get("info") or {}
    servers = []
    for s in list_mcp_servers():
        # `info` uses the key pattern `{name}_tools` set in runner.py.
        count = int(info.get(f"{s.name}_tools", 0) or 0)
        servers.append({**s.as_dict(), "tool_count": count})
    return {"servers": servers}


@app.get("/runs")
async def list_runs(limit: int = 50) -> Dict[str, Any]:
    store: Optional[RunStore] = _state.get("store")
    if store is None:
        return JSONResponse({"error": "store not ready"}, status_code=503)
    limit = max(1, min(500, limit))
    return {"runs": store.list_runs(limit=limit)}


@app.delete("/runs/{run_id}")
async def delete_run(run_id: str):
    store: Optional[RunStore] = _state.get("store")
    if store is None:
        return JSONResponse({"error": "store not ready"}, status_code=503)
    if not store.delete_run(run_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"deleted": run_id}


@app.patch("/runs/{run_id}")
async def update_run(run_id: str, request: Request):
    """Update the user-facing display name. Body: ``{"name": "string"}``.
    Empty/whitespace clears the name (display falls back to incident id)."""
    store: Optional[RunStore] = _state.get("store")
    if store is None:
        return JSONResponse({"error": "store not ready"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if not isinstance(body, dict) or "name" not in body:
        return JSONResponse({"error": "missing 'name' field"}, status_code=400)
    name = body.get("name")
    if name is not None and not isinstance(name, str):
        return JSONResponse({"error": "'name' must be a string or null"}, status_code=400)
    if not store.set_run_name(run_id, name):
        return JSONResponse({"error": "not found"}, status_code=404)
    row = store.get_run(run_id)
    return row if row is not None else {"id": run_id, "name": name}


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    """Stream a run's frames as SSE in seq order.

    A run still executing is followed: after the stored frames, the stream
    keeps polling the store for new ones until the run ends, then closes
    with ``done``. A finished run (or a stale 'running' row left by a
    restart) replays once and closes. No artificial pacing.

    Each frame carries its seq as the SSE ``id``, so when the browser's
    EventSource reconnects after a dropped connection it sends
    ``Last-Event-ID`` and the stream resumes after that frame.
    """
    store: Optional[RunStore] = _state.get("store")
    if store is None:
        return JSONResponse({"error": "store not ready"}, status_code=503)
    run = store.get_run(run_id)
    if run is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        last_seq = int(request.headers.get("last-event-id", ""))
    except ValueError:
        last_seq = None

    async def stream() -> AsyncIterator[str]:
        seen = -1
        if last_seq is None:
            # A synthetic start frame tells the UI the preset, incident and models.
            # The run's actual started_at keeps elapsed times on the
            # original run's baseline.
            yield _sse(
                "start",
                {
                    "preset": run["preset"],
                    "incident_id": run["incident_id"],
                    "run_id": run_id,
                    "following": run_id in _active_runs,
                    "models": store.start_payload(run_id).get("models", {}),
                    "at": run["started_at"],
                },
            )
        else:
            seen = last_seq
        while True:
            # Sample liveness BEFORE draining: once the run has ended, this
            # last drain still picks up every frame it wrote before ending.
            active = run_id in _active_runs
            for ev in store.iter_events(run_id, after_seq=seen):
                seen = ev["seq"]
                # The stored "start" and "done" frames are replaced by the
                # synthetic ones sent before and after this loop.
                if ev["kind"] in ("start", "done"):
                    continue
                # The events table's `at` is authoritative for replay.
                yield _sse(ev["kind"], {**ev["payload"], "at": ev["at"]}, event_id=seen)
            if not active:
                break
            await asyncio.sleep(_FOLLOW_POLL_S)
        ended = store.get_run(run_id) or run
        yield _sse(
            "done",
            {"status": ended["status"], "at": ended.get("ended_at") or ended["started_at"]},
            event_id=seen + 1,
        )

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)


class RunRequest(BaseModel):
    incident_id: str
    preset: str = "full"
    # None means every skill / server in the registry; an empty list means none.
    skills: Optional[list[str]] = None
    servers: Optional[list[str]] = None
    # Role -> gateway alias, for this run only. A missing role uses the
    # server's setting (GET /models).
    models: Dict[str, str] = {}


@app.post("/runs", status_code=202)
async def start_run(req: RunRequest):
    """Start a run in the background; follow it with ``GET /runs/{id}/events``."""
    make_supervisor = _state.get("make_supervisor")
    store: Optional[RunStore] = _state.get("store")
    incidents: Optional[Dict[str, Any]] = _state.get("incidents")
    if make_supervisor is None or store is None or incidents is None:
        return JSONResponse({"error": "agent not ready"}, status_code=503)

    incident = incidents.get(req.incident_id)
    if incident is None:
        return JSONResponse(
            {"error": f"incident {req.incident_id} not found"}, status_code=404
        )

    model_overrides = {
        role: resolve_model(req.models.get(role), alias) for role, alias in _run_models().items()
    }
    supervisor = make_supervisor(
        None if req.skills is None else set(req.skills),
        None if req.servers is None else set(req.servers),
        model_overrides,
    )

    # The supervisor sees the full incident payload inline so it can run even
    # without the PagerDuty MCP server (sub-agents adapt via their per-toggle
    # prompts).
    prompt = _build_prompt(req.preset, json.dumps(incident["payload"], indent=2, default=str))

    # Default run name from the incident title - users can rename later via
    # PATCH /runs/{id} from the history list.
    title = incident.get("title")
    run_id = store.create_run(
        preset=req.preset,
        incident_id=req.incident_id,
        prompt=prompt,
        name=title if isinstance(title, str) and title.strip() else None,
    )
    _set_incident_status(req.incident_id, "in_progress", run_id=run_id)
    _active_runs[run_id] = asyncio.create_task(
        _execute_run(run_id, supervisor, prompt, req.preset, req.incident_id, model_overrides)
    )
    return {"run_id": run_id}


@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    task = _active_runs.get(run_id)
    if task is None:
        return JSONResponse({"error": "run is not executing"}, status_code=409)
    task.cancel()
    return {"cancelled": run_id}


async def _execute_run(
    run_id: str,
    supervisor: Any,
    prompt: str,
    preset: str,
    incident_id: str,
    models: Optional[Dict[str, str]] = None,
) -> None:
    """Drive the supervisor and store every translated frame.

    The four async ``@tool`` closures on the supervisor push every event
    their sub-agent emits onto the ``current_event_queue`` ContextVar's
    queue (asyncio.create_task copies the current context); the supervisor's
    own events go onto the same queue, tagged ``"supervisor"``.
    """
    store: RunStore = _state["store"]
    seq = 0
    status, error_type, error_message = "done", None, None

    def emit(kind: str, data: Dict[str, Any]) -> None:
        nonlocal seq
        # Wall-clock time on every frame, so live and replayed runs show the
        # same per-tool and per-agent timings.
        data = {**data, "at": now_ms()}
        store.append_event(run_id, seq=seq, kind=kind, source=data.get("source"), payload=data)
        seq += 1

    try:
        # The role -> alias map lets the dashboard price the run per agent.
        emit(
            "start",
            {"preset": preset, "incident_id": incident_id, "run_id": run_id, "models": models or {}},
        )
        # What the supervisor starts with; each sub-agent's handoff follows
        # from inside its @tool closure.
        emit("handoff", {"source": "supervisor", **agent_context(supervisor, prompt)})
        # One trace per run: every span created inside - Strands' own
        # included - carries the run and incident ids. The driver task must
        # be created inside this block so it inherits the context.
        with tracing.run_context(
            run_id=run_id,
            incident_id=incident_id,
            agent_version=os.getenv("AGENT_VERSION", "0.1.0"),
        ):
            queue: asyncio.Queue = asyncio.Queue()
            token = current_event_queue.set(queue)

            async def drive_supervisor() -> None:
                try:
                    async for event in supervisor.stream_async(prompt):
                        await queue.put(("supervisor", event))
                except Exception as e:  # noqa: BLE001 - surface in the UI
                    await queue.put(("__error__", {"message": str(e), "type": type(e).__name__}))
                finally:
                    await queue.put(("__done__", None))

            driver = asyncio.create_task(drive_supervisor())
            try:
                while True:
                    source, event = await queue.get()
                    if source == "__done__":
                        break
                    if source == "__error__":
                        status, error_type, error_message = "error", event["type"], event["message"]
                        emit("agent_error", event)
                        break
                    for kind, data in _translate(source, event):
                        emit(kind, data)
                emit("done", {})
            finally:
                current_event_queue.reset(token)
                if not driver.done():
                    driver.cancel()
                    try:
                        await driver
                    except (asyncio.CancelledError, Exception):
                        pass
    except asyncio.CancelledError:
        status, error_type, error_message = "cancelled", "Cancelled", "Run stopped"
        emit("agent_error", {"message": "Run stopped", "type": "Cancelled"})
    except Exception as e:  # noqa: BLE001 - a bug here must still close the run
        logger.exception("run %s crashed", run_id)
        status, error_type, error_message = "error", type(e).__name__, str(e)
        emit("agent_error", {"message": str(e), "type": type(e).__name__})
    finally:
        store.finish_run(
            run_id, status=status, error_type=error_type, error_message=error_message
        )
        # After finish_run: every frame is stored, so a follower's final
        # drain sees the whole run before it closes.
        _active_runs.pop(run_id, None)
        # "completed" covers every terminal state; the run row has the outcome.
        _set_incident_status(incident_id, "completed", run_id=run_id)
        # Push spans now rather than on the batch timer, so the trace is in
        # Phoenix by the time the UI shows the run as done. In a thread: an
        # unreachable collector must not hold anything up.
        asyncio.get_running_loop().run_in_executor(None, tracing.flush)


def _translate(source: str, event: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    """Map one Strands ``stream_async`` event to ``(kind, data)`` tuples.

    The Strands event shape is loose: lifecycle flags, text deltas
    (``event["data"]``), reasoning deltas (``event["reasoningText"]``),
    streaming tool-use updates (``event["current_tool_use"]``), and
    completed messages (``event["message"]``) - the latter carries tool
    results when role=="user" and the content contains a ``toolResult``
    block.

    ``source`` is ``"supervisor"`` for events emitted by the top-level
    agent, or the @tool closure name for events forwarded from sub-agents.
    Every emitted frame carries ``source`` so the dashboard can render a
    nested timeline. Tool-use IDs are namespaced with ``"{source}:{id}"``
    to avoid collisions between sub-agents.
    """
    if event.get("init_event_loop") or event.get("start_event_loop"):
        return

    # Queued by the supervisor's @tool closures as a sub-agent starts (see
    # agent.sub_agents.supervisor.agent_context) - not a Strands event.
    handoff = event.get("handoff")
    if isinstance(handoff, dict):
        yield "handoff", {"source": source, **handoff}
        return

    # End-of-stream from a Strands Agent: ``AgentResultEvent`` carries the
    # final ``AgentResult`` whose ``.metrics`` is an ``EventLoopMetrics``.
    # Surface tokens + latency before swallowing the terminal frame so the
    # UI doesn't have to duplicate the math.
    result = event.get("result")
    if result is not None:
        try:
            metrics = result.metrics  # type: ignore[union-attr]
            usage = getattr(metrics, "accumulated_usage", {}) or {}
            perf = getattr(metrics, "accumulated_metrics", {}) or {}
            yield "metrics", {
                "source": source,
                "inputTokens": int(usage.get("inputTokens", 0) or 0),
                "outputTokens": int(usage.get("outputTokens", 0) or 0),
                "totalTokens": int(usage.get("totalTokens", 0) or 0),
                # Strands' Usage TypedDict carries cache hits/writes when the
                # underlying provider reports them (Anthropic prompt caching).
                "cacheReadTokens": int(usage.get("cacheReadInputTokens", 0) or 0),
                "cacheWriteTokens": int(usage.get("cacheWriteInputTokens", 0) or 0),
                "latencyMs": int(perf.get("latencyMs", 0) or 0),
                "cycles": int(getattr(metrics, "cycle_count", 0) or 0),
            }
        except Exception:  # noqa: BLE001 - never let metrics extraction break the run
            pass
        return

    if event.get("complete") or event.get("force_stop"):
        return  # outer ``done`` frame closes the stream

    if "data" in event and event["data"]:
        yield "text", {"source": source, "delta": str(event["data"])}
        return

    if event.get("reasoning") and "reasoningText" in event:
        yield "reasoning", {"source": source, "delta": str(event["reasoningText"])}
        return

    current_tool = event.get("current_tool_use")
    if current_tool:
        raw_id = current_tool.get("toolUseId") or ""
        yield "tool", {
            "source": source,
            "id": f"{source}:{raw_id}",
            "name": current_tool.get("name"),
            "input": current_tool.get("input"),
        }
        return

    message = event.get("message")
    if isinstance(message, dict):
        role = message.get("role")
        if role == "user":
            for item in message.get("content") or []:
                if isinstance(item, dict) and "toolResult" in item:
                    tool_result = item["toolResult"]
                    raw_id = tool_result.get("toolUseId") or ""
                    parts = []
                    for piece in tool_result.get("content") or []:
                        if isinstance(piece, dict) and "text" in piece:
                            parts.append(piece["text"])
                    yield "tool_result", {
                        "source": source,
                        "id": f"{source}:{raw_id}",
                        "content": "".join(parts),
                        "status": tool_result.get("status", "success"),
                    }
        elif role == "assistant":
            yield "assistant_done", {"source": source}
            # Live per-LLM-call usage. Strands attaches a Usage TypedDict to
            # every assistant message it builds (input/output/total + cache
            # read/write when the provider reports them). The agent's
            # ``EventLoopMetrics.accumulated_usage`` we later emit as
            # ``metrics`` is the sum of these - so the client treats
            # ``metrics`` as authoritative and uses ``metrics_delta`` for
            # live updates while the run is still in flight.
            metadata = message.get("metadata") or {}
            usage = metadata.get("usage") or {}
            if isinstance(usage, dict) and usage:
                yield "metrics_delta", {
                    "source": source,
                    "inputTokens": int(usage.get("inputTokens", 0) or 0),
                    "outputTokens": int(usage.get("outputTokens", 0) or 0),
                    "totalTokens": int(usage.get("totalTokens", 0) or 0),
                    "cacheReadTokens": int(usage.get("cacheReadInputTokens", 0) or 0),
                    "cacheWriteTokens": int(usage.get("cacheWriteInputTokens", 0) or 0),
                }


if __name__ == "__main__":
    import uvicorn

    # 8000 is already taken by the lenses-mcp container (see
    # harness/stack/docker-compose.yml), so default to 8765.
    port = int(os.getenv("AGENT_PORT", "8765"))
    uvicorn.run("agent.server:app", host="0.0.0.0", port=port, reload=False)
