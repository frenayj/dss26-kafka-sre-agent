"""Live PagerDuty reads (REST API v2) for the agent server's incident poller.

Two reads - the open-incident inbox and one incident by id - that feed real
PagerDuty incidents into the dashboard queue in ``PAGERDUTY_MODE=live`` (see
``agent.server._poll_pagerduty``). The agent itself does not use this module:
its PagerDuty tools come from PagerDuty's hosted MCP server.

Two details of the real API matter, and both are handled here so a live
incident reaches the supervisor in the same shape as a fixture one:

1. **Custom details live on the alert, not the incident.** When Datadog (or
   any monitoring integration) fires into PagerDuty, the payload it sends
   lands in ``alert.body.details``. ``GET /incidents/{id}`` never returns it.
   The fixture incident carries ``custom_details`` inline because that is the
   shape the triage prompt and the UI read, so this module fetches the
   incident's alerts and folds the first alert's details up onto the incident.
   Without that fold, the incident the supervisor receives would carry no
   monitor query, no tags and no metric value.

2. **The list endpoint returns bare incident objects**, not the
   ``{"incident": {...}}`` envelope the show endpoint uses. Both are
   normalised to the envelope here so callers have one shape to handle.

Read-only by construction: this module issues GETs and nothing else. It
shares ``PAGERDUTY_API_KEY`` - a User API Token - with the hosted MCP server.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from agent.config import (
    PAGERDUTY_API_KEY,
    PAGERDUTY_API_URL,
    PAGERDUTY_SERVICE_IDS,
)
from agent.integrations import IntegrationError

SYSTEM = "pagerduty"

# PD's versioning header. Without it the API serves an older response shape.
_ACCEPT = "application/vnd.pagerduty+json;version=2"

# Generous enough for a cold API, short enough that a hung upstream fails the
# tool call rather than stalling the whole agentic loop behind it.
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Which statuses count as "in the inbox". Resolved incidents are excluded -
# the demo's premise is an incident being worked, and including resolved ones
# buries it under weeks of history on any real account.
_OPEN_STATUSES = ("triggered", "acknowledged")


def _headers() -> Dict[str, str]:
    if not PAGERDUTY_API_KEY:
        raise IntegrationError(
            "PAGERDUTY_MODE=live but PAGERDUTY_API_KEY is not set",
            system=SYSTEM,
            hint=(
                "Set PAGERDUTY_API_KEY to a PagerDuty User API Token, or set "
                "PAGERDUTY_MODE=stub to use the bundled fixture incidents."
            ),
        )
    return {
        "Authorization": f"Token token={PAGERDUTY_API_KEY}",
        "Accept": _ACCEPT,
        "Content-Type": "application/json",
    }


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """GET one PagerDuty path, translating transport + HTTP errors uniformly."""
    url = f"{PAGERDUTY_API_URL}{path}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers=_headers(), params=params)
    except httpx.HTTPError as exc:
        raise IntegrationError(
            f"PagerDuty request failed: {type(exc).__name__}: {exc}",
            system=SYSTEM,
            hint=f"Could not reach {PAGERDUTY_API_URL}.",
        ) from exc

    if resp.status_code == 401:
        raise IntegrationError(
            "PagerDuty rejected the API key (401)",
            system=SYSTEM,
            hint="Check PAGERDUTY_API_KEY - it should be a User API Token.",
        )
    if resp.status_code == 403:
        raise IntegrationError(
            "PagerDuty denied the request (403)",
            system=SYSTEM,
            hint=(
                "A User API Token only sees what its user can see - use the "
                "token of a user with access to this service."
            ),
        )
    if resp.status_code == 404:
        raise IntegrationError(
            f"PagerDuty returned 404 for {path}", system=SYSTEM
        )
    if resp.status_code == 429:
        raise IntegrationError(
            "PagerDuty rate-limited the request (429)",
            system=SYSTEM,
            hint="Retry shortly, or narrow the query with PAGERDUTY_SERVICE_IDS.",
        )
    if resp.status_code >= 400:
        raise IntegrationError(
            f"PagerDuty returned {resp.status_code} for {path}: "
            f"{resp.text[:300]}",
            system=SYSTEM,
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise IntegrationError(
            f"PagerDuty returned a non-JSON body for {path}", system=SYSTEM
        ) from exc


def _fetch_alerts(incident_id: str) -> List[Dict[str, Any]]:
    """Return the incident's alerts, or [] if they cannot be read.

    Alerts are supplementary: an incident without them is still a usable
    triage input, just a thinner one. So a failure here is swallowed rather
    than failing the whole ``get_incident`` call - losing the monitor payload
    degrades the answer, losing the incident ends the run.
    """
    try:
        body = _get(f"/incidents/{incident_id}/alerts", {"limit": 10})
    except IntegrationError:
        return []
    alerts = body.get("alerts")
    return alerts if isinstance(alerts, list) else []


def _fold_alert_details(incident: Dict[str, Any], alerts: List[Dict[str, Any]]) -> None:
    """Lift the first alert's monitoring payload onto the incident, in place.

    This is the compatibility seam with the fixture back-end: the triage
    prompt and the UI both read ``incident.custom_details``, which is where a
    PagerDuty *webhook* puts the integration payload but where the REST API
    does not. An existing ``custom_details`` is never overwritten.
    """
    if not alerts:
        return

    incident["alerts"] = [
        {
            "id": a.get("id"),
            "summary": a.get("summary"),
            "status": a.get("status"),
            "severity": a.get("severity"),
            "created_at": a.get("created_at"),
            "integration": (a.get("integration") or {}).get("summary"),
        }
        for a in alerts
        if isinstance(a, dict)
    ]

    first_body = (alerts[0] or {}).get("body") or {}
    details = first_body.get("details")
    if isinstance(details, dict) and not incident.get("custom_details"):
        incident["custom_details"] = details
    # ``contexts`` is where Datadog attaches its links (snapshot, monitor).
    contexts = first_body.get("contexts")
    if contexts:
        incident.setdefault("alert_contexts", contexts)


def _envelope(incident: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a bare incident object in the ``{"incident": ...}`` envelope."""
    return incident if "incident" in incident else {"incident": incident}


def get_incident(incident_id: str) -> Dict[str, Any]:
    """Fetch one incident, enriched with its alert payload.

    Returns the same ``{"incident": {...}}`` envelope the fixture back-end
    returns. Raises :class:`IntegrationError` on any failure to fetch the
    incident itself.
    """
    body = _get(f"/incidents/{incident_id}")
    incident = body.get("incident")
    if not isinstance(incident, dict):
        raise IntegrationError(
            f"PagerDuty returned no incident object for {incident_id}",
            system=SYSTEM,
        )
    _fold_alert_details(incident, _fetch_alerts(incident_id))
    return {"incident": incident}


def list_incidents(limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch the most recent open incidents, newest first.

    Returns a list of ``{"incident": {...}}`` envelopes so the caller can
    apply the same projection it applies to fixture payloads. Alerts are NOT
    fetched here: one extra API call per row would turn an inbox listing into
    a rate-limit problem, and the inbox projection does not read them.
    """
    params: Dict[str, Any] = {
        "limit": max(1, min(100, int(limit))),
        "sort_by": "created_at:desc",
        "statuses[]": list(_OPEN_STATUSES),
    }
    if PAGERDUTY_SERVICE_IDS:
        params["service_ids[]"] = list(PAGERDUTY_SERVICE_IDS)

    body = _get("/incidents", params)
    incidents = body.get("incidents")
    if not isinstance(incidents, list):
        raise IntegrationError(
            "PagerDuty returned no incidents array", system=SYSTEM
        )
    return [_envelope(i) for i in incidents if isinstance(i, dict)]
