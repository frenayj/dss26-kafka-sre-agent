"""Static descriptor of the five MCP servers the demo wires up.

Mirrors :mod:`agent.skills_registry` but for MCP servers: the UI's toggle
list at ``GET /mcp_servers`` reads from here, the supervisor factory
validates enabled names against this set, and each entry advertises which
sub-agent it powers so the user can predict the impact of disabling it.

This is hard-coded rather than reflected from ``mcp_clients.py`` because
the names + descriptions are first-class UX strings, not implementation
detail; and there's only ever going to be a small fixed set for the demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from agent.config import (
    CONFLUENCE_DRY_RUN,
    CONFLUENCE_MODE,
    GITHUB_MODE,
    GITHUB_ORG,
    PAGERDUTY_MODE,
    SLACK_DRY_RUN,
    SLACK_MODE,
)


@dataclass(frozen=True)
class McpServerInfo:
    """One MCP server the demo wires up.

    Attributes:
        name: Stable identifier - matches the key in
            ``runner._list_tools()`` and the ``servers=`` CSV the UI sends.
        description: One-sentence UX string for the toggle row.
        sub_agent: Which sub-agent loses functionality when this server
            is disabled. Used by the UI to surface the impact.
    """

    name: str
    description: str
    sub_agent: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "sub_agent": self.sub_agent,
        }


def _label(mode: str) -> str:
    """Prefix a server's description with the back-end actually serving it.

    The toggle row is the only place an operator sees which servers are live,
    and "Simulated PagerDuty" next to a real incident would be a lie the UI
    tells on every run - so the label is derived from the mode, not written
    into the string.
    """
    return "Live" if mode == "live" else "Simulated"


MCP_SERVERS: Tuple[McpServerInfo, ...] = (
    McpServerInfo(
        name="pagerduty",
        description=(
            # Live is PagerDuty's own hosted MCP server, not our stub - the
            # tool names differ, and it writes (ack + notes, see pagerduty_guard).
            "Live PagerDuty (hosted MCP) - browse_incidents, manage_incidents "
            "(acknowledge + notes only)"
            if PAGERDUTY_MODE == "live"
            else "Simulated PagerDuty - get_incident, list_recent_incidents"
        ),
        # Live mode also hands the tools to the reporter for its closing note.
        sub_agent="triage",
    ),
    McpServerInfo(
        name="lenses",
        description="Lenses MCP - read-only Kafka topics, groups, SQL, metrics",
        sub_agent="diagnosis",
    ),
    McpServerInfo(
        name="github",
        description=(
            f"{_label(GITHUB_MODE)} GitHub ({GITHUB_ORG}) - search_pull_requests, "
            "search_code, pull_request_read, list_commits (read-only)"
        ),
        sub_agent="forensics",
    ),
    McpServerInfo(
        name="confluence",
        description=(
            f"{_label(CONFLUENCE_MODE)} Confluence - search_pages, get_page "
            "(team knowledge base), create_page (RCA write-up)"
            + (" [dry run]" if CONFLUENCE_MODE == "live" and CONFLUENCE_DRY_RUN else "")
        ),
        sub_agent="triage + reporter",
    ),
    McpServerInfo(
        name="slack",
        description=(
            f"{_label(SLACK_MODE)} Slack - post_message (on-call summary)"
            # Live-but-dry-run is a third state, and the operator needs to
            # see it here: "Live Slack" alone would imply real pages.
            + (" [dry run]" if SLACK_MODE == "live" and SLACK_DRY_RUN else "")
        ),
        sub_agent="reporter",
    ),
)


MCP_SERVER_NAMES: frozenset[str] = frozenset(s.name for s in MCP_SERVERS)


def list_mcp_servers() -> Tuple[McpServerInfo, ...]:
    """Return the canonical list of MCP servers in display order."""
    return MCP_SERVERS
