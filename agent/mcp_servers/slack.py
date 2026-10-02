"""Slack MCP server (stdio): the reporter's on-call summary.

Owns the Slack tool contract the reporter sub-agent is written against:

  * ``post_message(channel, text)`` - returns a Slack-style ack.

:class:`LiveSlack` posts to a real workspace via
:mod:`agent.integrations.slack`, behind a channel policy, a dry-run default
and a dedupe ledger. The harness's test double
(``harness/stubs/slack_mcp.py``) serves the same tool with a back-end that
only logs.

Whatever the back-end, the message is rendered as a Rich panel on the
operator's terminal and appended to ``logs/slack.log``: with the test double
it is the output, with the live back-end it is the receipt - the operator can
see what the agent said to a real channel without leaving the terminal.

Run directly with:
    python -m agent.mcp_servers.slack
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Protocol

from mcp.server.fastmcp import FastMCP
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agent.config import SLACK_DRY_RUN
from agent.integrations import IntegrationError
from agent.mcp_servers._receipts import ensure_logs_dir

logger = logging.getLogger(__name__)

# stdio transport reserves stdout for MCP framing - render the demo box on
# stderr so it shows up in the operator's terminal without corrupting the
# protocol stream.
_console = Console(file=sys.stderr, force_terminal=True)

_LOG_NAME = "slack.log"


class SlackBackend(Protocol):
    """What ``post_message`` needs from a back-end."""

    name: str  # the MCP server's name
    description: str  # what calling post_message means, for the model

    def post(self, channel: str, text: str) -> Dict[str, Any]:
        """Send the message and return the ack; raise IntegrationError on failure."""

    def outcome(self, ack: Dict[str, Any]) -> str:
        """One word for the receipt: posted, dry-run, deduplicated..."""


class LiveSlack:
    """A real Slack workspace."""

    name = "slack"

    # The description says the workspace is REAL because it changes what
    # calling the tool MEANS. A model that believes it is writing to a demo log
    # will phrase an on-call summary differently from one that knows it is
    # paging real humans.
    description = (
        "Post a Slack message to the given channel in the REAL workspace. "
        "This notifies actual people - post once, and only when you have a "
        "finding worth paging on. The ack reports what happened: `ts` set "
        "means posted, `dry_run` means the credential was verified but "
        "nothing was sent, `deduplicated` means an identical message was "
        "already posted recently."
        + (
            " Dry-run is currently ON, so no message will actually be sent."
            if SLACK_DRY_RUN
            else ""
        )
    )

    def post(self, channel: str, text: str) -> Dict[str, Any]:
        from agent.integrations import slack as sl

        return sl.post_message(channel, text)

    def outcome(self, ack: Dict[str, Any]) -> str:
        if ack.get("deduplicated"):
            return "deduplicated"
        if ack.get("dry_run"):
            return "dry-run"
        return "posted"


def _render(channel: str, text: str, timestamp: str, outcome: str) -> None:
    """Show the message in the operator's terminal, labelled with its fate."""
    border = {
        "posted": "bold green",
        "dry-run": "bold yellow",
        "deduplicated": "bold blue",
        "logged": "bold magenta",
        "failed": "bold red",
    }.get(outcome, "bold magenta")
    _console.print(
        Panel(
            Text(text),
            # Parentheses, not brackets: Rich parses "[logged]" in a
            # title as console markup and silently drops it.
            title=f"Slack → #{channel.lstrip('#')}  ({outcome})",
            subtitle=f"{timestamp}",
            border_style=border,
            padding=(1, 2),
        )
    )


def _log(channel: str, text: str, timestamp: str, outcome: str) -> None:
    """Append to ``logs/slack.log``."""
    log_path = ensure_logs_dir() / _LOG_NAME
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] #{channel.lstrip('#')} ({outcome})\n")
        handle.write(text.rstrip() + "\n")
        handle.write("-" * 80 + "\n")


def build_server(backend: SlackBackend) -> FastMCP:
    """A Slack MCP server over ``backend``."""
    mcp = FastMCP(backend.name)

    @mcp.tool(description=backend.description)
    def post_message(channel: str, text: str) -> str:
        """Send the message via the back-end and return a Slack-style ack."""
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            ack = backend.post(channel, text)
        except IntegrationError as exc:
            logger.warning("slack post_message failed: %s", exc)
            _render(channel, text, timestamp, "failed")
            _log(channel, text, timestamp, f"failed: {exc}")
            return json.dumps(exc.as_payload(), indent=2)

        outcome = backend.outcome(ack)
        target = ack.get("channel", channel)
        _render(target, text, timestamp, outcome)
        _log(target, text, timestamp, outcome)
        return json.dumps(ack, indent=2, default=str)

    return mcp


def main() -> None:
    logger.info("slack MCP server starting (dry_run=%s)", SLACK_DRY_RUN)
    build_server(LiveSlack()).run(transport="stdio")


if __name__ == "__main__":
    main()
