"""Drive a real PagerDuty account for the live demo: set it up, page it, reset it.

Three subcommands, all idempotent, stdlib only (no venv needed):

    python3 harness/pagerduty/pagerduty_demo.py setup                # services + Events v2 integrations + P1 rule
    python3 harness/pagerduty/pagerduty_demo.py page consumer-lag    # fire a scenario's alert
    python3 harness/pagerduty/pagerduty_demo.py resolve              # resolve every open incident on the demo services

Why paging goes through the Events API
--------------------------------------
The demo's incidents are Datadog monitor alerts, and triage reads the monitor
payload - ``custom_details.tags`` carries the cluster, consumer group and
topic. A Datadog -> PagerDuty integration delivers that payload as an
Events API v2 event, so ``page`` sends exactly that: the incident's
``custom_details`` (from ``harness/scenarios/<name>/incident.json``, the same
alert the stub serves) to the service's routing key. PagerDuty then creates a real alert + incident and notifies on-call, which
is the point. An incident created by hand in the PagerDuty UI has no alert and
no tags, and triage would have nothing to extract.

The numbers are not the fixture's. For a consumer-lag alert, ``page`` reads
the group's lag on the cluster, waits until it passes the monitor's threshold,
and sends that as the last evaluated value (see lag_alert.py) - so the alert
agrees with what Lenses shows the agent.

Priority is not settable through the Events API, so ``setup`` adds a service
orchestration rule that marks every event on the demo services P1 - otherwise
the incident shows up with no priority and triage reports severity ``null``.

Credentials
-----------
``PAGERDUTY_API_KEY`` must be a **User API Token** (My Profile -> User Settings
-> Create API User Token) - the same token the agent's PagerDuty MCP uses.
It is read from the environment, falling back to the repo's .env file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from harness import scenarios  # noqa: E402
from harness.pagerduty import lag_alert  # noqa: E402

# Each scenario's incident names the PagerDuty service its alert is routed to,
# so the services `setup` creates stay in lockstep with what triage expects.

INTEGRATION_NAME = "Datadog"
INTEGRATION_TYPE = "events_api_v2_inbound_integration"
DEMO_PRIORITY = "P1"


def _load_env_file() -> None:
    """Fill unset variables from the repo's .env, like python-dotenv would."""
    path = REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

API_URL = os.environ.get("PAGERDUTY_API_URL", "https://api.pagerduty.com").rstrip("/")
# EU accounts live on api.eu / events.eu; derive one from the other.
EVENTS_URL = API_URL.replace("://api.", "://events.") + "/v2/enqueue"
API_KEY = os.environ.get("PAGERDUTY_API_KEY", "").strip()


def _die(msg: str) -> None:
    sys.exit(f"[pagerduty] ERROR: {msg}")


def _request(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        _die(f"{method} {url} -> HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        _die(f"{method} {url} -> {exc.reason}")
    return json.loads(raw) if raw else {}


def _api(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not API_KEY:
        _die("PAGERDUTY_API_KEY is not set (a User API Token - see this script's docstring)")
    url = f"{API_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    return _request(
        method,
        url,
        body,
        {
            "Authorization": f"Token token={API_KEY}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
        },
    )


def _incident(scenario: str) -> Dict[str, Any]:
    return scenarios.load(scenario).incident()["incident"]


def _demo_service_names() -> List[str]:
    return sorted({_incident(s)["service"]["name"] for s in scenarios.names()})


def _find_service(name: str) -> Optional[Dict[str, Any]]:
    res = _api("GET", "/services", params={"query": name, "include[]": "integrations"})
    return next((s for s in res.get("services", []) if s["name"] == name), None)


def _routing_key(service: Dict[str, Any]) -> Optional[str]:
    for integ in service.get("integrations") or []:
        if integ.get("type") == INTEGRATION_TYPE and integ.get("integration_key"):
            return integ["integration_key"]
    return None


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


def _escalation_policy() -> Dict[str, Any]:
    wanted = os.environ.get("PAGERDUTY_ESCALATION_POLICY", "").strip()
    policies = _api("GET", "/escalation_policies").get("escalation_policies", [])
    if not policies:
        _die("the account has no escalation policy - create one that pages you first")
    if wanted:
        match = next((p for p in policies if p["name"] == wanted), None)
        if match is None:
            _die(f"no escalation policy named {wanted!r}")
        return match
    return policies[0]


def _ensure_service(name: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    service = _find_service(name)
    if service is None:
        service = _api(
            "POST",
            "/services",
            {
                "service": {
                    "type": "service",
                    "name": name,
                    "description": "Kafka SRE agent demo (DSS26) - paged by harness/pagerduty/pagerduty_demo.py",
                    "escalation_policy": {
                        "id": policy["id"],
                        "type": "escalation_policy_reference",
                    },
                    "alert_creation": "create_alerts_and_incidents",
                    "incident_urgency_rule": {"type": "constant", "urgency": "high"},
                }
            },
        )["service"]
        print(f"  created service {name} ({service['id']})")
    else:
        print(f"  service {name} exists ({service['id']})")

    if _routing_key(service) is None:
        _api(
            "POST",
            f"/services/{service['id']}/integrations",
            {
                "integration": {
                    "type": INTEGRATION_TYPE,
                    "name": INTEGRATION_NAME,
                    "service": {"id": service["id"], "type": "service_reference"},
                }
            },
        )
        print(f"  added Events API v2 integration '{INTEGRATION_NAME}'")
        service = _find_service(name) or service
    return service


def _ensure_priority_rule(service: Dict[str, Any], priority_id: str) -> None:
    sid = service["id"]
    _api(
        "PUT",
        f"/event_orchestrations/services/{sid}",
        {
            "orchestration_path": {
                "sets": [{"id": "start", "rules": []}],
                "catch_all": {"actions": {"priority": priority_id}},
            }
        },
    )
    _api("PUT", f"/event_orchestrations/services/{sid}/active", {"active": True})
    print(f"  every event on this service is now {DEMO_PRIORITY}")


def cmd_setup(_: argparse.Namespace) -> None:
    policy = _escalation_policy()
    print(f"escalation policy: {policy['name']} ({policy['id']})")
    priorities = _api("GET", "/priorities").get("priorities", [])
    p1 = next((p for p in priorities if p["name"] == DEMO_PRIORITY), None)
    if p1 is None:
        print(f"  WARNING: no {DEMO_PRIORITY} priority on this account - incidents will have no priority")

    ids = []
    for name in _demo_service_names():
        print(f"\n{name}")
        service = _ensure_service(name, policy)
        if p1 is not None:
            _ensure_priority_rule(service, p1["id"])
        ids.append(service["id"])

    print("\nAdd to your env file so the agent only watches the demo services:\n")
    print(f"  PAGERDUTY_SERVICE_IDS={','.join(ids)}")


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------


def cmd_page(args: argparse.Namespace) -> None:
    inc = _incident(args.scenario)
    details = dict(inc.get("custom_details") or {})
    tags = {t.split(":", 1)[0]: t.split(":", 1)[1] for t in details.get("tags", []) if ":" in t}

    service = _find_service(inc["service"]["name"])
    key = _routing_key(service) if service else None
    if key is None:
        _die(f"no Events API v2 integration on {inc['service']['name']!r} - run `setup` first")

    message = (inc.get("body") or {}).get("details")
    if details.get("metric") == "kafka.consumer_lag":
        try:
            details = lag_alert.measure(details)
        except RuntimeError as exc:
            _die(str(exc))
        message = lag_alert.alert_message(details)
        print(f"[page] {details['metric_value']:,} records of lag (threshold {details['threshold_critical']:,})")

    # A fresh dedup key per page: a fixed one would fold a second page of the
    # same scenario into the first incident instead of opening a new one.
    dedup_key = f"{inc['incident_key']}:{int(time.time())}"
    event = {
        "routing_key": key,
        "event_action": "trigger",
        "dedup_key": dedup_key,
        "client": "Datadog",
        "client_url": details.get("alert_link"),
        "payload": {
            "summary": inc["title"],
            "source": tags.get("kafka_cluster", "datadog"),
            "severity": "critical",
            "component": tags.get("consumer_group") or tags.get("connector"),
            "group": inc["service"]["name"],
            "class": details.get("monitor_name"),
            "custom_details": {**details, "message": message},
        },
        "links": (
            [{"href": details["alert_link"], "text": "Datadog monitor"}]
            if details.get("alert_link")
            else []
        ),
    }
    res = _request("POST", EVENTS_URL, event, {"Content-Type": "application/json"})
    print(f"paged {inc['service']['name']}: {res.get('status')} - {res.get('message')} (dedup_key {dedup_key})")


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


def open_incidents() -> List[Dict[str, Any]]:
    """Triggered or acknowledged incidents on the demo services."""
    ids = [s["id"] for s in (_find_service(n) for n in _demo_service_names()) if s]
    if not ids:
        return []
    return _api(
        "GET",
        "/incidents",
        params={
            "statuses[]": ["triggered", "acknowledged"],
            "service_ids[]": ids,
            "limit": 100,
        },
    ).get("incidents", [])


def cmd_resolve(_: argparse.Namespace) -> None:
    incidents = open_incidents()
    if not incidents:
        print("no open incidents on the demo services")
        return
    email = _api("GET", "/users/me")["user"]["email"]
    req = urllib.request.Request(
        f"{API_URL}/incidents",
        data=json.dumps(
            {
                "incidents": [
                    {"id": i["id"], "type": "incident_reference", "status": "resolved"}
                    for i in incidents
                ]
            }
        ).encode(),
        method="PUT",
        headers={
            "Authorization": f"Token token={API_KEY}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
            "From": email,
        },
    )
    with urllib.request.urlopen(req, timeout=20):
        pass
    print(f"resolved {len(incidents)}: {', '.join(i['id'] for i in incidents)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="create the demo services, integrations and P1 rule").set_defaults(func=cmd_setup)
    page = sub.add_parser("page", help="fire a demo alert into PagerDuty")
    page.add_argument("scenario", choices=scenarios.names())
    page.set_defaults(func=cmd_page)
    sub.add_parser("resolve", help="resolve open incidents on the demo services").set_defaults(func=cmd_resolve)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
