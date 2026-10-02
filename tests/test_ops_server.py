"""The operator console's server: status parsing, the origin guard, Stop.

The guard matters because the server runs make targets that merge PRs and
page people: a web page in another tab must not be able to trigger them.
"""

from __future__ import annotations

import http.client
import json
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness" / "ops"))
import ops_server as ops  # noqa: E402

GROUPS_OUTPUT = """
GROUP                    TOPIC                            PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG    CONSUMER-ID   HOST        CLIENT-ID
fraud-decisioning-engine cards.authorisation.requested.v1 0          100             1600            1500   rdkafka-1     /172.21.0.7 rdkafka
fraud-decisioning-engine cards.authorisation.requested.v1 1          50              50              -      rdkafka-1     /172.21.0.7 rdkafka
"""


def test_consumer_lag_is_summed_across_partitions(monkeypatch):
    monkeypatch.setattr(ops, "_run", lambda cmd, timeout=15: GROUPS_OUTPUT)
    assert ops.check_consumer() == {"group": "fraud-decisioning-engine", "lag": 1500, "active": True}


def test_stack_flags_health_and_one_shots(monkeypatch):
    rows = "\n".join([
        "dss26-agent-server-1\trunning\tUp 3 minutes (healthy)\tagent-server",
        "dss26-seeder-1\texited\tExited (0) 2 minutes ago\tseeder",
        "lenses-mcp\trunning\tUp 3 minutes\tlenses-mcp",
    ])
    monkeypatch.setattr(ops, "_run", lambda cmd, timeout=15: rows)
    by_service = {c["service"]: c for c in ops.check_stack()["containers"]}
    assert by_service["agent-server"]["health"] == "healthy"
    assert by_service["seeder"]["one_shot"] is True
    assert by_service["lenses-mcp"]["health"] is None


@pytest.fixture
def server(monkeypatch):
    started = []

    def fake_start(action):
        job = ops.Job(id=1, action=action, started_at=0)
        started.append(action.name)
        return True, job

    monkeypatch.setattr(ops, "start_job", fake_start)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ops.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], started
    httpd.shutdown()


def _request(port, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    return resp.status, dict(resp.getheaders()), resp.read()


DASHBOARD = "http://localhost:8080"


def test_the_dashboard_can_start_an_action(server):
    port, started = server
    status, headers, body = _request(port, "POST", "/actions/preflight",
                                     {"Origin": DASHBOARD, "Content-Type": "application/json"}, "{}")
    assert status == 202 and started == ["preflight"]
    assert headers["Access-Control-Allow-Origin"] == DASHBOARD
    assert json.loads(body)["job"]["action"] == "preflight"


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example", "Content-Type": "application/json"},  # another site
    {"Origin": DASHBOARD, "Content-Type": "text/plain"},  # a form post skips the preflight
    {"Content-Type": "application/x-www-form-urlencoded"},
])
def test_other_callers_cannot_start_actions(server, headers):
    port, started = server
    status, _, _ = _request(port, "POST", "/actions/reset", headers, "x")
    assert status == 403 and started == []


def test_preflight_is_only_granted_to_the_dashboard(server):
    port, _ = server
    assert _request(port, "OPTIONS", "/actions/reset", {"Origin": "https://evil.example"})[0] == 403
    status, headers, _ = _request(port, "OPTIONS", "/actions/reset", {"Origin": DASHBOARD})
    assert status == 204 and headers["Access-Control-Allow-Origin"] == DASHBOARD


def test_unknown_action_is_404(server):
    port, _ = server
    status, _, _ = _request(port, "POST", "/actions/rm-rf",
                            {"Origin": DASHBOARD, "Content-Type": "application/json"}, "{}")
    assert status == 404


def test_stop_kills_the_whole_process_group(monkeypatch):
    job = ops.Job(id=7, action=ops.ACTIONS_BY_NAME["reset"], started_at=0)
    job.proc = subprocess.Popen(["sh", "-c", "sleep 30 & sleep 30; wait"], start_new_session=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    monkeypatch.setattr(ops, "_job", job)
    threading.Thread(target=ops._pump, args=(job,), daemon=True).start()
    time.sleep(0.3)
    assert ops.stop_job() is True
    deadline = time.time() + 5
    while job.ended_at is None and time.time() < deadline:
        time.sleep(0.05)
    assert job.status == "stopped"
    left = subprocess.run(["pgrep", "-g", str(job.proc.pid)], capture_output=True, text=True)
    assert left.stdout.strip() == ""
