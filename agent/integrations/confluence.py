"""Live Confluence back-end (Confluence Cloud REST API).

Serves the same three tools the fixture back-end does, against a real
Confluence Cloud site:

  * ``search_pages`` / ``get_page`` - read the team's knowledge base (runbooks,
    standards, past incidents). Reads ignore dry run: they change nothing.
  * ``create_page`` - publish the RCA.

Search uses the v1 CQL endpoint, because v2 has no full-text search; pages
are read and written through v2. Page bodies come back as Confluence storage
XHTML and are flattened to plain text for the model (``storage_to_text``).

``create_page`` is a write into a space other people watch, so like Slack it
carries three guardrails, applied in order:

1. **Space policy.** ``CONFLUENCE_SPACE`` pins every page to one space key,
   overriding the ``DSS26`` the reporter prompt names. The ack says so
   (``requested_space``) rather than redirecting silently.

2. **Title dedupe.** Confluence rejects a second page with the same title in
   a space, and retries (the agentic loop's and the gateway's) re-run the
   reporter with the same title. So an existing page with that title is
   returned as ``deduplicated`` instead of surfacing a 400 the model would
   misread as "publishing failed".

3. **Dry run**, on by default (``config.CONFLUENCE_DRY_RUN``). The credential
   and the space are still resolved against the real API, so a dry run proves
   the integration works; only the page creation is withheld.

One translation the fixture back-end never needed: the reporter writes
Markdown, and Confluence stores XHTML ("storage format"). See
:func:`markdown_to_storage`.

Never falls back to the fixture back-end - see :mod:`agent.integrations`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html.entities import name2codepoint
from html.parser import HTMLParser
from typing import Any, Dict, Optional

import httpx

from agent.config import (
    CONFLUENCE_API_TOKEN,
    CONFLUENCE_BASE_URL,
    CONFLUENCE_DRY_RUN,
    CONFLUENCE_EMAIL,
    CONFLUENCE_PARENT_PAGE_ID,
    CONFLUENCE_SPACE,
)
from agent.integrations import IntegrationError

SYSTEM = "confluence"

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def _check_config() -> None:
    missing = [
        name
        for name, value in (
            ("CONFLUENCE_BASE_URL", CONFLUENCE_BASE_URL),
            ("CONFLUENCE_EMAIL", CONFLUENCE_EMAIL),
            ("CONFLUENCE_API_TOKEN", CONFLUENCE_API_TOKEN),
        )
        if not value
    ]
    if missing:
        raise IntegrationError(
            f"CONFLUENCE_MODE=live but {', '.join(missing)} not set",
            system=SYSTEM,
            hint=(
                "Set CONFLUENCE_BASE_URL (https://<site>.atlassian.net/wiki), "
                "CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN, or set "
                "CONFLUENCE_MODE=stub to keep writing to logs/confluence.log."
            ),
        )


def _request(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call one Confluence REST path, translating errors uniformly."""
    _check_config()
    url = f"{CONFLUENCE_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.request(
                method,
                url,
                params=params,
                json=json,
                auth=(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise IntegrationError(
            f"Confluence request failed: {type(exc).__name__}: {exc}",
            system=SYSTEM,
            hint=f"Could not reach {CONFLUENCE_BASE_URL}.",
        ) from exc

    if resp.status_code == 401:
        raise IntegrationError(
            "Confluence rejected the credentials (401)",
            system=SYSTEM,
            hint="Check CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN belong together.",
        )
    if resp.status_code == 403:
        raise IntegrationError(
            f"Confluence denied {method} {path} (403)",
            system=SYSTEM,
            hint="The account lacks permission to add pages in that space.",
        )
    if resp.status_code == 404:
        raise IntegrationError(
            f"Confluence returned 404 for {path}",
            system=SYSTEM,
            hint=(
                "Check CONFLUENCE_BASE_URL ends in /wiki, and that "
                "CONFLUENCE_PARENT_PAGE_ID (if set) exists."
            ),
        )
    if resp.status_code == 429:
        raise IntegrationError(
            f"Confluence rate-limited the request (retry after "
            f"{resp.headers.get('Retry-After', '?')}s)",
            system=SYSTEM,
        )
    if resp.status_code >= 400:
        raise IntegrationError(
            f"Confluence returned {resp.status_code} for {method} {path}: "
            f"{resp.text[:300]}",
            system=SYSTEM,
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise IntegrationError(
            f"Confluence returned a non-JSON body for {path}", system=SYSTEM
        ) from exc


# ---------------------------------------------------------------------------
# Markdown -> storage format
# ---------------------------------------------------------------------------


def markdown_to_storage(body: str) -> str:
    """Render the reporter's Markdown as Confluence storage-format XHTML.

    Storage format is strict XML: one stray ``<`` and Confluence rejects the
    whole page. Model output routinely contains things that look like markup
    (``lag > 50k``, ``<consumer-group>``, ``&``), so raw HTML and entity
    pass-through are switched off and everything is escaped as text.
    """
    import markdown  # imported here so stub mode never needs the dependency

    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="xhtml",
    )
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    md.inlinePatterns.deregister("entity")
    return _NAMED_ENTITY.sub(_xml_safe_entity, md.convert(body or ""))


# Python-Markdown's serializer leaves anything shaped like ``&name;`` alone,
# even with entity pass-through off. XML only defines five named entities, so
# ``&nbsp;`` from the model would make the page unparseable.
_NAMED_ENTITY = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_XML_ENTITIES = frozenset({"amp", "lt", "gt", "quot", "apos"})


def _xml_safe_entity(match: "re.Match[str]") -> str:
    """Keep XML's own entities, make HTML ones numeric, escape the rest."""
    name = match.group(1)
    if name in _XML_ENTITIES:
        return match.group(0)
    codepoint = name2codepoint.get(name)
    if codepoint is not None:
        return f"&#{codepoint};"
    return f"&amp;{name};"


# ---------------------------------------------------------------------------
# Guardrails + lookups
# ---------------------------------------------------------------------------


def resolve_space(requested: str) -> str:
    """Apply the space policy and return the space KEY to publish into."""
    if CONFLUENCE_SPACE:
        return CONFLUENCE_SPACE
    key = (requested or "").strip()
    if not key:
        raise IntegrationError("no space given", system=SYSTEM)
    return key


def _space_id(key: str) -> str:
    """Resolve a space key to the numeric id v2 page creation requires."""
    body = _request("GET", "/api/v2/spaces", params={"keys": key, "limit": 1})
    results = body.get("results") or []
    if not results:
        raise IntegrationError(
            f"Confluence space '{key}' not found",
            system=SYSTEM,
            hint=(
                "The space key does not exist or the account cannot see it. "
                "Set CONFLUENCE_SPACE to a space key you can write to."
            ),
        )
    return str(results[0]["id"])


def _find_page(space_id: str, title: str) -> Optional[Dict[str, Any]]:
    body = _request(
        "GET",
        "/api/v2/pages",
        params={"space-id": space_id, "title": title, "status": "current", "limit": 1},
    )
    results = body.get("results") or []
    return results[0] if results else None


def _page_url(page: Dict[str, Any]) -> Optional[str]:
    links = page.get("_links") or {}
    webui = links.get("webui")
    if not webui:
        return None
    return f"{(links.get('base') or CONFLUENCE_BASE_URL).rstrip('/')}{webui}"


# ---------------------------------------------------------------------------
# Reads: the team knowledge base
# ---------------------------------------------------------------------------

# A page body goes straight into the model's context; one sprawling page must
# not crowd out the case file.
_MAX_BODY_CHARS = 20_000

_PAGE_ID_IN_URL = re.compile(r"/pages/(\d+)")
_HIGHLIGHT = re.compile(r"@@@(?:end)?hl@@@")


def _cql_string(text: str) -> str:
    """Quote ``text`` as a CQL string literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _scoped(cql: str) -> str:
    """Restrict a CQL query to the pinned space, when there is one.

    Without CONFLUENCE_SPACE the search covers every space the account can
    see - fine on a demo site, too broad anywhere else.
    """
    if CONFLUENCE_SPACE:
        return f"space = {_cql_string(CONFLUENCE_SPACE)} AND {cql}"
    return cql


def _search(cql: str, limit: int) -> list:
    body = _request(
        "GET", "/rest/api/search", params={"cql": _scoped(cql), "limit": limit}
    )
    return [r for r in body.get("results") or [] if isinstance(r, dict)]


def _hit(result: Dict[str, Any]) -> Dict[str, Any]:
    """Project a v1 search result onto the fixture result shape."""
    content = result.get("content") or {}
    webui = (content.get("_links") or {}).get("webui") or result.get("url")
    return {
        "id": str(content.get("id") or result.get("id") or ""),
        "title": content.get("title") or result.get("title"),
        "url": f"{CONFLUENCE_BASE_URL}{webui}" if webui else None,
        "last_modified": result.get("lastModified"),
        "excerpt": _HIGHLIGHT.sub("", result.get("excerpt") or "").strip(),
    }


def search_pages(query: str, limit: int = 5) -> Dict[str, Any]:
    """Full-text search over pages, best match first."""
    query = (query or "").strip()
    if not query:
        raise IntegrationError("empty search query", system=SYSTEM)
    limit = max(1, min(10, int(limit)))
    results = _search(f"type = page AND text ~ {_cql_string(query)}", limit)
    return {
        "query": query,
        "space": CONFLUENCE_SPACE or None,
        "results": [_hit(r) for r in results],
    }


def _resolve_page_id(page: str) -> str:
    """Turn whatever the model has - an id, a URL, a title - into a page id.

    Alert runbook links are often not Confluence's own ``/pages/<id>/`` form
    (the demo's are ``.../pages/Runbooks/Consumer-Lag-Critical``), so anything
    without a numeric id is looked up by the words of its last path segment.
    """
    ref = (page or "").strip()
    if ref.isdigit():
        return ref
    match = _PAGE_ID_IN_URL.search(ref)
    if match:
        return match.group(1)
    words = re.sub(r"[-_+]+", " ", ref.rstrip("/").rsplit("/", 1)[-1]).strip()
    if not words:
        raise IntegrationError("no page given", system=SYSTEM)
    results = _search(f"type = page AND title ~ {_cql_string(words)}", 1)
    if not results:
        raise IntegrationError(
            f"no Confluence page matches '{words}'",
            system=SYSTEM,
            hint="Use search_pages to find the page and pass its id.",
        )
    return _hit(results[0])["id"]


class _StorageText(HTMLParser):
    """Flatten Confluence storage XHTML into readable plain text."""

    _BLOCK = {"p", "div", "table", "ul", "ol", "pre", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("br", "tr"):
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in self._BLOCK:
            self.out.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self._BLOCK or tag.startswith("h"):
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(data)

    def unknown_decl(self, data):
        # Code macros keep their text in CDATA sections.
        if data.startswith("CDATA["):
            self.out.append(data[len("CDATA["):])


def storage_to_text(storage: str) -> str:
    parser = _StorageText()
    parser.feed(storage or "")
    parser.close()
    text = "".join(parser.out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def get_page(page: str) -> Dict[str, Any]:
    """Read one page as plain text, by id, URL or title."""
    page_id = _resolve_page_id(page)
    body = _request(
        "GET", f"/api/v2/pages/{page_id}", params={"body-format": "storage"}
    )
    text = storage_to_text(((body.get("body") or {}).get("storage") or {}).get("value", ""))
    if len(text) > _MAX_BODY_CHARS:
        text = text[:_MAX_BODY_CHARS] + "\n\n[page truncated]"
    return {
        "id": str(body.get("id") or page_id),
        "title": body.get("title"),
        "url": _page_url(body),
        "last_modified": (body.get("version") or {}).get("createdAt"),
        "body": text,
    }


# ---------------------------------------------------------------------------
# The one write
# ---------------------------------------------------------------------------


def create_page(space: str, title: str, body: str) -> Dict[str, Any]:
    """Publish an RCA page, subject to the space policy, dedupe and dry run.

    Returns the fixture back-end's ack shape (``id`` / ``url`` / ``space`` /
    ``title`` / ``created_at``) plus whichever of ``dry_run`` /
    ``deduplicated`` applied, so the model can tell "published", "would have
    published" and "already published" apart.
    """
    target = resolve_space(space)
    requested = (space or "").strip()

    ack: Dict[str, Any] = {"space": target, "title": title}
    if requested and requested != target:
        ack["requested_space"] = requested
        ack["note"] = "space overridden by CONFLUENCE_SPACE"

    # Resolving the space is also the credential check, so it runs in every
    # path - including dry run, which is what makes a dry run evidence.
    space_id = _space_id(target)

    existing = _find_page(space_id, title)
    if existing:
        return {
            **ack,
            "id": existing.get("id"),
            "url": _page_url(existing),
            "created_at": existing.get("createdAt"),
            "deduplicated": True,
            "note": (
                "a page with this title already exists in the space; it was "
                "not created again"
            ),
        }

    if CONFLUENCE_DRY_RUN:
        return {
            **ack,
            "id": None,
            "url": None,
            "created_at": None,
            "dry_run": True,
            "note": (
                "CONFLUENCE_DRY_RUN is on (the default in live mode) - the "
                "credential and space were verified but no page was created, "
                "so there is no URL to cite. Set CONFLUENCE_DRY_RUN=false to "
                "publish."
            ),
        }

    payload: Dict[str, Any] = {
        "spaceId": space_id,
        "status": "current",
        "title": title,
        "body": {"representation": "storage", "value": markdown_to_storage(body)},
    }
    if CONFLUENCE_PARENT_PAGE_ID:
        payload["parentId"] = CONFLUENCE_PARENT_PAGE_ID

    page = _request("POST", "/api/v2/pages", json=payload)
    return {
        **ack,
        "id": page.get("id"),
        "url": _page_url(page),
        "created_at": page.get("createdAt")
        or datetime.now(timezone.utc).isoformat(),
    }
