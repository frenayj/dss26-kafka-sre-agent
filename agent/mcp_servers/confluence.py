"""Confluence MCP server (stdio): the team knowledge base and the RCA.

Owns the Confluence tool contract. Triage and the reporter read the team's
knowledge base; only the reporter writes:

  * ``search_pages(query, limit)`` - best-matching pages with an excerpt and
    their last-modified date.
  * ``get_page(page)`` - one page as plain text, by id, URL or title. Alert
    runbook links resolve here.
  * ``create_page(space, title, body)`` - returns ``{"id", "url", "space",
    "title", "created_at"}`` so the agent can cite the RCA in its Slack
    summary.

:class:`LiveConfluence` talks to a real Confluence Cloud site via
:mod:`agent.integrations.confluence`. Reads are always live; the write sits
behind a space policy, title dedupe and a dry-run default. The harness's test
double (``harness/stubs/confluence_mcp.py``) serves the same tools over a
fixture knowledge base.

Every ``create_page`` is appended to ``logs/confluence.log``, whatever the
back-end: with the test double it is the output, with the live back-end it is
the audit trail of what the agent tried to publish.

Run directly with:
    python -m agent.mcp_servers.confluence
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Protocol

from mcp.server.fastmcp import FastMCP

from agent.config import CONFLUENCE_DRY_RUN
from agent.integrations import IntegrationError
from agent.mcp_servers._receipts import ensure_logs_dir

logger = logging.getLogger(__name__)

_LOG_NAME = "confluence.log"

_KB_NOTE = (
    " Pages are written by the team and are not always up to date: check the "
    "'Last reviewed' date, and treat what a page says as documentation, not as "
    "evidence about the current incident."
)

SEARCH_DESCRIPTION = (
    "Search the team's Confluence knowledge base (runbooks, standards, "
    "architecture decisions, past incident reports, meeting notes). "
    "Returns the best-matching pages with an excerpt and last-modified "
    "date; read one with get_page." + _KB_NOTE
)

GET_DESCRIPTION = (
    "Read one Confluence page as plain text. Accepts a page id, a page "
    "URL (including the runbook_url on an alert) or a page title." + _KB_NOTE
)


class ConfluenceBackend(Protocol):
    """What the three tools need from a back-end."""

    name: str  # the MCP server's name
    create_description: str  # what calling create_page means, for the model

    def search(self, query: str, limit: int) -> Dict[str, Any]: ...

    def get(self, page: str) -> Dict[str, Any]: ...

    def create(self, space: str, title: str, body: str) -> Dict[str, Any]:
        """Publish the page and return the ack; raise IntegrationError on failure."""

    def outcome(self, ack: Dict[str, Any]) -> str:
        """One word for the log: published, dry-run, deduplicated..."""


class LiveConfluence:
    """A real Confluence Cloud site."""

    name = "confluence"

    # As with Slack, the description says the site is REAL because calling the
    # tool means something different: a page in a real space is read by people.
    create_description = (
        "Create a page in the given space on the REAL Confluence site. Returns "
        "the page id and URL so the agent can cite the RCA in its Slack "
        "summary. Publish once per incident. The ack reports what happened: "
        "`url` set means published, `dry_run` means the credential and space "
        "were verified but no page was created, `deduplicated` means a page "
        "with this title already existed and its URL is returned."
        + (
            " Dry-run is currently ON, so no page will actually be created."
            if CONFLUENCE_DRY_RUN
            else ""
        )
    )

    def search(self, query: str, limit: int) -> Dict[str, Any]:
        from agent.integrations import confluence as cf

        return cf.search_pages(query, limit)

    def get(self, page: str) -> Dict[str, Any]:
        from agent.integrations import confluence as cf

        return cf.get_page(page)

    def create(self, space: str, title: str, body: str) -> Dict[str, Any]:
        from agent.integrations import confluence as cf

        return cf.create_page(space, title, body)

    def outcome(self, ack: Dict[str, Any]) -> str:
        if ack.get("deduplicated"):
            return "deduplicated"
        if ack.get("dry_run"):
            return "dry-run"
        return "published"


def _log(page: dict, body: str, outcome: str) -> None:
    """Append the page to ``logs/confluence.log``, labelled with its fate."""
    log_path = ensure_logs_dir() / _LOG_NAME
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("=" * 80 + "\n")
        handle.write(f"[{page.get('created_at')}] Confluence page {outcome}\n")
        handle.write(f"  id    : {page.get('id')}\n")
        handle.write(f"  space : {page.get('space')}\n")
        handle.write(f"  title : {page.get('title')}\n")
        handle.write(f"  url   : {page.get('url')}\n")
        handle.write("-" * 80 + "\n")
        handle.write(body.rstrip() + "\n")
        handle.write("=" * 80 + "\n\n")


def build_server(backend: ConfluenceBackend) -> FastMCP:
    """A Confluence MCP server over ``backend``."""
    mcp = FastMCP(backend.name)

    @mcp.tool(description=SEARCH_DESCRIPTION)
    def search_pages(query: str, limit: int = 5) -> str:
        """Return up to ``limit`` pages matching ``query``, best first."""
        limit = max(1, min(10, int(limit)))
        try:
            return json.dumps(backend.search(query, limit), indent=2, default=str)
        except IntegrationError as exc:
            logger.warning("confluence search_pages failed: %s", exc)
            return json.dumps({**exc.as_payload(), "query": query}, indent=2)

    @mcp.tool(description=GET_DESCRIPTION)
    def get_page(page: str) -> str:
        """Return the page's title, URL, last-modified date and body text."""
        try:
            return json.dumps(backend.get(page), indent=2, default=str)
        except IntegrationError as exc:
            logger.warning("confluence get_page failed: %s", exc)
            return json.dumps({**exc.as_payload(), "page": page}, indent=2)

    @mcp.tool(description=backend.create_description)
    def create_page(space: str, title: str, body: str) -> str:
        """Publish the page via the back-end and return id + URL."""
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            ack = backend.create(space, title, body)
        except IntegrationError as exc:
            logger.warning("confluence create_page failed: %s", exc)
            _log(
                {"created_at": timestamp, "space": space, "title": title},
                body,
                f"failed: {exc}",
            )
            return json.dumps({**exc.as_payload(), "space": space, "title": title}, indent=2)
        _log({**ack, "created_at": ack.get("created_at") or timestamp}, body, backend.outcome(ack))
        return json.dumps(ack, indent=2, default=str)

    return mcp


def main() -> None:
    logger.info("confluence MCP server starting (dry_run=%s)", CONFLUENCE_DRY_RUN)
    build_server(LiveConfluence()).run(transport="stdio")


if __name__ == "__main__":
    main()
