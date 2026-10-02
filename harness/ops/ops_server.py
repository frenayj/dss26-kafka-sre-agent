#!/usr/bin/env python3
"""Operator console backend: the demo's live status, and buttons for its make targets.

    make ops        # then open http://localhost:8080/#/ops

It runs on the host, next to your Docker CLI and `gh` login, and executes the
same make targets you would type, one at a time, streaming their output to
the dashboard's hidden ``#/ops`` page. It listens on 127.0.0.1 only and
accepts actions only from the dashboard's own origins (a JSON content type is
required, so a browser always sends a CORS preflight first).

    GET  /status            the latest snapshot of every status source
    GET  /actions           the buttons: make targets with a label and group
    POST /actions/<name>    start one (409 while another job runs)
    GET  /job?after=N       the current or last job, and its output from line N
    POST /job/stop          stop the running job

Standard library only, like the rest of the host-side scripts.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "harness"
# The status checks reuse the GitHub and PagerDuty scripts' own helpers, and
# the buttons come from the scenario registry.
sys.path[:0] = [str(REPO_ROOT), str(HARNESS / "pagerduty"), str(HARNESS / "github_org")]

from harness import scenarios  # noqa: E402


def _load_env(path: Path) -> None:
    """Fill unset variables from a KEY=value file (the env file, ports.parallel)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _port(var: str, default: str) -> str:
    return os.environ.get(var) or default


def _configure() -> None:
    """Derive the endpoints from the environment (re-run once the env files are loaded)."""
    global PORT, SR_URL, CONNECT_URL, AGENT_URL, UI_PORT, ALLOWED_ORIGINS
    PORT = int(_port("OPS_PORT", "8770"))
    SR_URL = os.environ.get("SCHEMA_REGISTRY_PROD") or f"http://localhost:{_port('HOST_PORT_SR_PROD', '8081')}"
    CONNECT_URL = os.environ.get("CONNECT_PROD_URL") or f"http://localhost:{_port('HOST_PORT_CONNECT_PROD', '8093')}"
    AGENT_URL = f"http://localhost:{_port('HOST_PORT_AGENT', '8765')}"
    UI_PORT = _port("HOST_PORT_UI", "8080")
    ALLOWED_ORIGINS = {
        f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (UI_PORT, "5173")
    }


_configure()

KAFKA_CONTAINER = "demo-kafka-prod"
CONSUMER_GROUP = "fraud-decisioning-engine"
SUBJECT = "cards.authorisation.requested.v1-value"
ONE_SHOT_SERVICES = {"create-configs", "seeder"}


# ---------------------------------------------------------------------------
# Actions: the make targets the console can run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Action:
    name: str
    label: str
    group: str  # live | steps | prepare
    kind: str  # what it does, for the button's icon
    description: str
    make: tuple[str, ...]  # the make target and its arguments
    confirm: bool = False  # pages a human, so the UI asks first


def _actions() -> list[Action]:
    """The shared steps, plus three buttons per scenario folder."""
    per_scenario = [
        (
            Action(f"live-{s.name}", f"{s.title} incident", "live", "live",
                   f"Reset, resolve old pages, break the cluster, wait {s.page_delay_s}s, "
                   "then page PagerDuty.", ("live", f"SCENARIO={s.name}"), True),
            Action(f"induce-{s.name}", f"Break: {s.title.lower()}", "steps", "induce",
                   s.summary, ("induce", f"SCENARIO={s.name}")),
            Action(f"page-{s.name}", f"Page: {s.title.lower()}", "steps", "page",
                   f"Send the {s.title.lower()} alert to PagerDuty.",
                   ("page", f"SCENARIO={s.name}"), True),
        )
        for s in scenarios.all_scenarios()
    ]
    return [
        *(live for live, _, _ in per_scenario),
        Action("reset", "Reset", "steps", "reset",
               "Restore a healthy cluster; merge a revert if a culprit PR is on main.", ("reset",)),
        Action("pd-resolve", "Resolve pages", "steps", "pd-resolve",
               "Resolve every open incident on the demo services.", ("pd-resolve",)),
        *(step for _, induce, page in per_scenario for step in (induce, page)),
        Action("gh-warmup", "Merge decoy PRs", "prepare", "gh-warmup",
               "Merge the day's decoy PRs; do it 30+ minutes before a live run.", ("gh-warmup",)),
        Action("preflight", "Preflight", "prepare", "preflight",
               "Check the env file, services and gateway.", ("preflight",)),
    ]


ACTIONS = _actions()
ACTIONS_BY_NAME = {a.name: a for a in ACTIONS}


# ---------------------------------------------------------------------------
# Jobs: one make target at a time, output kept in memory
# ---------------------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_MAX_LINES = 5000


@dataclass
class Job:
    id: int
    action: Action
    started_at: int
    status: str = "running"  # running | succeeded | failed | stopped
    exit_code: Optional[int] = None
    ended_at: Optional[int] = None
    lines: list[str] = field(default_factory=list)
    proc: Optional[subprocess.Popen] = None

    def summary(self) -> dict:
        return {
            "id": self.id, "action": self.action.name, "label": self.action.label,
            "status": self.status, "exit_code": self.exit_code,
            "started_at": self.started_at, "ended_at": self.ended_at,
        }


_job_lock = threading.Lock()
_job: Optional[Job] = None
_job_counter = 0


def _now_ms() -> int:
    return int(time.time() * 1000)


def start_job(action: Action) -> tuple[bool, Job]:
    """Start the action's make target; ``(False, running_job)`` if one is already running."""
    global _job, _job_counter
    with _job_lock:
        if _job is not None and _job.status == "running":
            return False, _job
        _job_counter += 1
        job = Job(id=_job_counter, action=action, started_at=_now_ms())
        job.lines.append(f"$ make {' '.join(action.make)}")
        job.proc = subprocess.Popen(
            ["make", "--no-print-directory", *action.make],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,  # its own process group, so Stop reaches every child
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        _job = job
    threading.Thread(target=_pump, args=(job,), daemon=True).start()
    return True, job


def _pump(job: Job) -> None:
    assert job.proc is not None and job.proc.stdout is not None
    for line in job.proc.stdout:
        job.lines.append(_ANSI.sub("", line.rstrip("\n")))
        if len(job.lines) > _MAX_LINES:
            del job.lines[1:1001]
    code = job.proc.wait()
    job.exit_code = code
    job.ended_at = _now_ms()
    if job.status == "running":
        job.status = "succeeded" if code == 0 else "failed"
    job.lines.append(f"[exit {code}]")


def stop_job() -> bool:
    with _job_lock:
        job = _job
        if job is None or job.status != "running" or job.proc is None:
            return False
        job.status = "stopped"
        try:
            os.killpg(job.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        return True


# ---------------------------------------------------------------------------
# Status: one poller thread per source, so a slow one never blocks the rest
# ---------------------------------------------------------------------------

_status: dict[str, Any] = {}
_status_lock = threading.Lock()


def _run(cmd: list[str], timeout: float = 15) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        lines = (out.stderr or out.stdout).strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"exit {out.returncode}")
    return out.stdout


def _get_json(url: str, timeout: float = 5) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def check_stack() -> dict:
    fmt = '{{.Names}}\t{{.State}}\t{{.Status}}\t{{.Label "com.docker.compose.service"}}'
    out = _run(["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=dss26",
                "--format", fmt])
    containers = []
    for line in out.splitlines():
        name, state, status, service = (line.split("\t") + ["", "", "", ""])[:4]
        health = next((h for h in ("unhealthy", "healthy", "starting") if f"({h}" in status), None)
        containers.append({"name": name, "service": service, "state": state, "status": status,
                           "health": health, "one_shot": service in ONE_SHOT_SERVICES})
    return {"containers": sorted(containers, key=lambda c: c["service"])}


def check_consumer() -> dict:
    out = _run(["docker", "exec", KAFKA_CONTAINER, "kafka-consumer-groups", "--bootstrap-server",
                "localhost:9092", "--describe", "--group", CONSUMER_GROUP])
    lag, members = 0, False
    for line in out.splitlines():
        cols = line.split()
        if len(cols) >= 7 and cols[0] == CONSUMER_GROUP:
            lag += int(cols[5]) if cols[5].isdigit() else 0
            members = members or cols[6] != "-"
    return {"group": CONSUMER_GROUP, "lag": lag, "active": members}


def check_schema() -> dict:
    latest = _get_json(f"{SR_URL}/subjects/{SUBJECT}/versions/latest")
    try:
        compat = _get_json(f"{SR_URL}/config/{SUBJECT}")["compatibilityLevel"]
    except urllib.error.HTTPError:  # no subject-level setting: the global one applies
        compat = _get_json(f"{SR_URL}/config")["compatibilityLevel"]
    return {"subject": SUBJECT, "version": latest["version"], "id": latest["id"],
            "compatibility": compat}


def check_connectors() -> dict:
    data = _get_json(f"{CONNECT_URL}/connectors?expand=status")
    connectors = []
    for name, info in sorted(data.items()):
        st = info.get("status", {})
        tasks = st.get("tasks", [])
        trace = next((t.get("trace", "") for t in tasks if t.get("state") == "FAILED"), "")
        connectors.append({
            "name": name,
            "state": st.get("connector", {}).get("state"),
            "tasks": [t.get("state") for t in tasks],
            "error": trace.splitlines()[0][:300] if trace else None,
        })
    return {"connectors": connectors}


def check_agent() -> dict:
    incidents = _get_json(f"{AGENT_URL}/incidents")["incidents"]
    runs = _get_json(f"{AGENT_URL}/runs?limit=1")["runs"]
    return {"incidents": incidents, "last_run": runs[0] if runs else None}


def check_github() -> dict:
    import scenario
    from catalog import load_repos
    from gh import GitHub

    if not scenario.github_scenarios_enabled():
        return {"enabled": False, "culprits": []}
    return {"enabled": True, "culprits": scenario.culprit_states(GitHub(), load_repos())}


def check_pagerduty() -> dict:
    if not os.environ.get("PAGERDUTY_API_KEY"):
        return {"enabled": False, "incidents": []}
    import pagerduty_demo

    try:
        incidents = pagerduty_demo.open_incidents()
    except SystemExit as exc:  # the script's _die() exits with its message
        raise RuntimeError(str(exc)) from None
    return {"enabled": True, "incidents": [
        {"id": i["id"], "status": i["status"], "title": i.get("title"),
         "url": i.get("html_url"), "created_at": i.get("created_at")}
        for i in incidents
    ]}


def _poll(name: str, check: Callable[[], dict], interval: float) -> None:
    while True:
        try:
            value = {**check(), "error": None}
        except Exception as exc:  # noqa: BLE001 - every failure is a status to show
            value = {"error": f"{type(exc).__name__}: {exc}"}
        with _status_lock:
            _status[name] = {**value, "checked_at": _now_ms()}
        time.sleep(interval)


POLLERS = [
    ("stack", check_stack, 5),
    ("consumer", check_consumer, 5),
    ("schema", check_schema, 5),
    ("connectors", check_connectors, 5),
    ("agent", check_agent, 3),
    ("pagerduty", check_pagerduty, 15),
    ("github", check_github, 30),
]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "ops/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if not self.path.startswith(("/status", "/job")):  # the UI polls these
            sys.stderr.write(f"[ops] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}\n")

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in ALLOWED_ORIGINS

    def _send(self, code: int, body: Any = None) -> None:
        data = json.dumps(body if body is not None else {}).encode()
        self.send_response(code)
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        if self.headers.get("Origin") not in ALLOWED_ORIGINS:
            self._send(403, {"error": "origin not allowed"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._origin_ok():
            self._send(403, {"error": "origin not allowed"})
            return
        url = urlparse(self.path)
        if url.path == "/status":
            with _status_lock:
                self._send(200, {"updated_at": _now_ms(), **_status})
        elif url.path == "/actions":
            self._send(200, {"actions": [a.__dict__ for a in ACTIONS]})
        elif url.path == "/job":
            after = int((parse_qs(url.query).get("after") or ["0"])[0] or 0)
            job = _job
            if job is None:
                self._send(200, {"job": None, "lines": [], "next": 0})
            else:
                lines = job.lines[after:]
                self._send(200, {"job": job.summary(), "lines": lines, "next": after + len(lines)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        # A JSON content type can't be sent cross-site without a preflight,
        # which do_OPTIONS only grants to the dashboard's origins.
        if not self._origin_ok() or not (self.headers.get("Content-Type") or "").startswith(
            "application/json"
        ):
            self._send(403, {"error": "origin or content type not allowed"})
            return
        path = urlparse(self.path).path
        if path.startswith("/actions/"):
            action = ACTIONS_BY_NAME.get(path.removeprefix("/actions/"))
            if action is None:
                self._send(404, {"error": "unknown action"})
                return
            started, job = start_job(action)
            if started:
                self._send(202, {"job": job.summary()})
            else:
                self._send(409, {"error": f"{job.action.name} is still running", "job": job.summary()})
        elif path == "/job/stop":
            stopped = stop_job()
            self._send(200 if stopped else 409, {"stopped": stopped})
        else:
            self._send(404, {"error": "not found"})


def main() -> None:
    # The same settings the scripts see: the parallel-port profile, then the env file.
    _load_env(REPO_ROOT / "ports.parallel")
    _load_env(REPO_ROOT / ".env")
    _configure()
    for name, check, interval in POLLERS:
        threading.Thread(target=_poll, args=(name, check, interval), daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[ops] listening on http://127.0.0.1:{PORT}")
    print(f"[ops] open http://localhost:{UI_PORT}/#/ops")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stop_job()


if __name__ == "__main__":
    main()
