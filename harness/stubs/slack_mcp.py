"""Slack MCP server (stdio) - a workspace that only logs.

The test double for :mod:`agent.mcp_servers.slack`: the same
``post_message`` tool, with a back-end that sends nothing. The agent server
renders the message as a Rich panel on the operator's terminal and appends it
to ``logs/slack.log``; nobody is notified.

Run directly with:
    python -m harness.stubs.slack_mcp
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from agent.mcp_servers.slack import build_server

logger = logging.getLogger(__name__)


class LogOnly:
    """A back-end for :func:`agent.mcp_servers.slack.build_server`."""

    # "-stub" so traces, logs and tool listings never leave anyone guessing
    # whether a run talked to a real workspace.
    name = "slack-stub"
    description = (
        "Post a Slack message to the given channel. The message is rendered as "
        "a Rich-styled panel on the operator's terminal (so it's visible on "
        "stage during the demo) and persisted to logs/slack.log. Returns the "
        "Slack-style ack."
    )

    def post(self, channel: str, text: str) -> Dict[str, Any]:
        return {"ok": True, "channel": channel, "ts": f"{time.time():.6f}"}

    def outcome(self, ack: Dict[str, Any]) -> str:
        return "logged"


def build() -> FastMCP:
    """The stub server (also what the tests drive)."""
    return build_server(LogOnly())


if __name__ == "__main__":
    logger.info("slack stub MCP server starting")
    build().run(transport="stdio")
