"""Confluence MCP server (stdio) - the team knowledge base, offline.

The test double for :mod:`agent.mcp_servers.confluence`: the same three
tools, over the Cards Platform knowledge base in :mod:`harness.stubs._kb_pages`
instead of a real site.

  * ``search_pages`` / ``get_page`` read the fixture pages. Alert runbook
    links resolve to them.
  * ``create_page`` publishes nothing: the agent server appends the page to
    ``logs/confluence.log`` and this back-end returns a made-up page in the
    knowledge base's real space, under "Incident reports".

Run directly with:
    python -m harness.stubs.confluence_mcp
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from agent.mcp_servers.confluence import build_server
from harness.stubs import _kb_pages as kb

logger = logging.getLogger(__name__)


# Words that match every page and so rank nothing.
_STOPWORDS = frozenset(
    "a an and are as at be by for from how in is it of on or the this to what "
    "when where which with".split()
)


def _norm(word: str) -> str:
    # Fold a plural so "incidents" finds "incident".
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _terms(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", text.lower())
    return [_norm(w) for w in words if w not in _STOPWORDS]


def _words(text: str) -> set:
    """Whole words of a field, plus the parts of hyphenated/dotted ones.

    Whole-word matching, not substrings: "ci" must not match "decisioning".
    """
    out = set()
    for w in _terms(text):
        out.add(w)
        out.update(_norm(part) for part in re.split(r"[._-]", w))
    return out


def _score(page: "kb.KbPage", terms: List[str]) -> int:
    """Rank like a title-weighted full-text search: title 3, labels 2, body 1."""
    title = _words(page.title)
    labels = _words(" ".join(page.labels))
    text = _words(" ".join((page.summary, *page.points)))
    return sum(3 * (t in title) + 2 * (t in labels) + (t in text) for t in terms)


def _search(query: str, limit: int) -> Dict[str, Any]:
    terms = _terms(query)
    ranked = sorted(
        ((score, p) for p in kb.PAGES if (score := _score(p, terms)) > 0),
        key=lambda sp: (-sp[0], sp[1].title),
    )
    return {
        "query": query,
        "space": kb.SPACE_KEY,
        "results": [
            {
                "id": p.page_id,
                "title": p.title,
                "url": p.url,
                "last_modified": p.reviewed,
                "excerpt": p.summary,
            }
            for _, p in ranked[:limit]
        ],
    }


def _find(ref: str) -> "kb.KbPage | None":
    """Resolve an id, a URL (including the alerts' runbook links) or a title."""
    ref = ref.strip()
    if ref.isdigit():
        return kb.BY_ID.get(ref)
    if "/pages/" in ref:
        tail = ref.split("/pages/", 1)[1].strip("/")
        head = tail.split("/", 1)[0]
        if head.isdigit():
            return kb.BY_ID.get(head)
        for page in kb.PAGES:
            if any(tail.lower() == a.lower() for a in page.aliases):
                return page
        ref = tail.rsplit("/", 1)[-1]
    wanted = re.sub(r"[-_+]+", " ", ref).strip().lower()
    for page in kb.PAGES:
        if wanted in (page.title.lower(), page.slug):
            return page
    # Same fallback the live back-end uses: best title match for the words.
    hits = [p for p in kb.PAGES if wanted and set(_terms(wanted)) <= _words(p.title)]
    return hits[0] if len(hits) == 1 else None


class KnowledgeBase:
    """A back-end for :func:`agent.mcp_servers.confluence.build_server`."""

    # "-stub" so traces, logs and tool listings never leave anyone guessing
    # whether a run talked to a real site.
    name = "confluence-stub"
    create_description = (
        "Create a Confluence page in the given space. Returns the page id and "
        "URL so the agent can cite the RCA in its Slack summary. The full body "
        "is appended to logs/confluence.log for demo inspection."
    )

    def search(self, query: str, limit: int) -> Dict[str, Any]:
        return _search(query, limit)

    def get(self, page: str) -> Dict[str, Any]:
        found = _find(page)
        if found is None:
            return {
                "error": "page not found",
                "page": page,
                "hint": "Use search_pages to find the page and pass its id.",
            }
        return {
            "id": found.page_id,
            "title": found.title,
            "url": found.url,
            "last_modified": found.reviewed,
            "body": found.body(),
        }

    def create(self, space: str, title: str, body: str) -> Dict[str, Any]:
        # Filed where the live back-end files it: the knowledge base's space,
        # under its "Incident reports" page, and overriding the space the
        # model asks for the way CONFLUENCE_SPACE does. The page itself is
        # simulated, so its link is Confluence-shaped but opens nothing.
        page_id = str(4_000_000_000 + uuid.uuid4().int % 1_000_000_000)
        page = {
            "id": page_id,
            "url": f"{kb.SITE_URL}/spaces/{kb.SPACE_KEY}/pages/{page_id}/{kb.title_slug(title)}",
            "space": kb.SPACE_KEY,
            "title": title,
            "parent_id": kb.INCIDENT_REPORTS_PAGE_ID,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if (space or "").strip() and space.strip() != kb.SPACE_KEY:
            page["requested_space"] = space.strip()
        return page

    def outcome(self, ack: Dict[str, Any]) -> str:
        return "created"


def build() -> FastMCP:
    """The stub server (also what the tests drive)."""
    return build_server(KnowledgeBase())


if __name__ == "__main__":
    logger.info("confluence stub MCP server starting")
    build().run(transport="stdio")
