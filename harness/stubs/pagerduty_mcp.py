"""PagerDuty MCP server (stdio) - the scenarios' incidents, offline.

Serves every scenario's alert (``harness/scenarios/*/incident.json``) behind
a minimal PagerDuty tool contract:

  * ``get_incident(incident_id)``  - the full incident payload as JSON.
  * ``list_recent_incidents()``    - a PD inbox view (id / title / severity /
    service / status / created_at).

Deterministic, offline, no credentials. This is ``PAGERDUTY_MODE=stub`` only:
live mode connects the agent to PagerDuty's own hosted MCP server instead
(see :func:`agent.mcp_clients.make_pagerduty_client`).

Run directly with:
    python -m harness.stubs.pagerduty_mcp
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from harness.scenarios import all_scenarios

logger = logging.getLogger(__name__)

# "-stub" so traces, logs and tool listings never leave anyone guessing
# whether a run talked to a real account.
mcp = FastMCP("pagerduty-stub")


def _incidents() -> List[Dict[str, Any]]:
    """Every scenario's incident, stamped now so it always looks freshly fired."""
    return [scenario.incident() for scenario in all_scenarios()]


def _summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Project a full incident payload down to an inbox-row summary."""
    inc = payload.get("incident") or payload
    return {
        "id": inc.get("id"),
        "title": inc.get("title") or inc.get("summary") or "(no title)",
        "severity": (inc.get("priority") or {}).get("name"),
        "service": (inc.get("service") or {}).get("name")
        or (inc.get("service") or {}).get("summary"),
        "status": inc.get("status"),
        "created_at": inc.get("created_at"),
    }


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


def _stub_get_incident(incident_id: str) -> Dict[str, Any]:
    for payload in _incidents():
        if payload["incident"]["id"] == incident_id:
            return payload
    return {"error": "incident not found", "incident_id": incident_id}


def _stub_list_incidents(limit: int) -> List[Dict[str, Any]]:
    return _incidents()[:limit]


@mcp.tool(
    description=(
        "Fetch a PagerDuty incident by id. Returns the full incident "
        "payload as JSON."
    )
)
def get_incident(incident_id: str) -> str:
    """Return the incident matching ``incident_id``, or an error payload."""
    return _dump(_stub_get_incident(incident_id))


@mcp.tool(
    description="List the most recent incidents in the PagerDuty inbox."
)
def list_recent_incidents(limit: int = 10) -> str:
    """Return an array of recent incident summaries (id / title / status / created_at)."""
    limit = max(1, min(100, int(limit)))
    return _dump([_summary(p) for p in _stub_list_incidents(limit)])


if __name__ == "__main__":
    logger.info("pagerduty stub MCP server starting")
    mcp.run(transport="stdio")
