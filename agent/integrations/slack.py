"""Live Slack back-end (Web API ``chat.postMessage``).

This is the first *write* integration, so most of the code here is guardrails
rather than transport. The transport is one POST; the interesting part is
everything that has to be true before that POST is allowed to happen.

Three protections, applied in order:

1. **Channel policy.** ``SLACK_DEFAULT_CHANNEL`` pins every post to one
   channel regardless of what the model asked for; failing that, an optional
   allowlist constrains the model's choice. The reporter prompt hardcodes
   ``#sre-oncall``, which will not exist in most workspaces, so without a
   pin the first live run is a ``channel_not_found`` at best and a post to
   somebody's real channel at worst.

2. **Dry run**, on by default (see ``config.SLACK_DRY_RUN``). Credentials and
   channel are still validated against the real API, so a dry run proves the
   integration works end to end; only the message is withheld.

3. **Deduplication.** Slack has no idempotency key for ``chat.postMessage``,
   so a retried run posts twice. Both the agentic loop and the LiteLLM
   gateway retry, and each retry re-runs the reporter, which makes duplicate
   pages the *expected* outcome rather than an edge case. A small on-disk
   ledger suppresses an identical ``(channel, text)`` within a TTL.

   The limit of that mechanism, stated plainly: it keys on exact text. A
   retry that re-renders with a different timestamp hashes differently and
   will post again. Content hashing catches the common case honestly; it is
   not a distributed idempotency guarantee, and the dry-run default is what
   actually protects a workspace.

Never falls back to the fixture back-end - see :mod:`agent.integrations`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, Optional

import httpx

from agent.config import (
    SLACK_API_URL,
    SLACK_BOT_TOKEN,
    SLACK_CHANNEL_ALLOWLIST,
    SLACK_DEDUPE_TTL_S,
    SLACK_DEFAULT_CHANNEL,
    SLACK_DRY_RUN,
    SLACK_LEDGER_PATH,
)
from agent.integrations import IntegrationError

logger = logging.getLogger(__name__)

SYSTEM = "slack"

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Ledger of what we have already posted, so a retried run does not page the
# channel twice. Deliberately a plain file: the agent has no shared state
# store, and a dedupe record that does not survive the process is a dedupe
# record that never fires. Its location is configurable precisely so the
# container can put it on a persisted volume (see config.SLACK_LEDGER_PATH).
_LEDGER_PATH = SLACK_LEDGER_PATH


def _headers() -> Dict[str, str]:
    if not SLACK_BOT_TOKEN:
        raise IntegrationError(
            "SLACK_MODE=live but SLACK_BOT_TOKEN is not set",
            system=SYSTEM,
            hint=(
                "Set SLACK_BOT_TOKEN to a bot token (xoxb-...) with the "
                "chat:write scope, or set SLACK_MODE=stub to keep writing to "
                "logs/slack.log."
            ),
        )
    return {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }


def _call(method: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call one Slack Web API method.

    Slack answers HTTP 200 for logical failures too, so the ``ok`` field is
    the only reliable success signal - checking the status code alone would
    report a ``missing_scope`` rejection as a successful post.
    """
    url = f"{SLACK_API_URL}/{method}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, headers=_headers(), json=payload or {})
    except httpx.HTTPError as exc:
        raise IntegrationError(
            f"Slack request failed: {type(exc).__name__}: {exc}",
            system=SYSTEM,
            hint=f"Could not reach {SLACK_API_URL}.",
        ) from exc

    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "?")
        raise IntegrationError(
            f"Slack rate-limited the request (retry after {retry_after}s)",
            system=SYSTEM,
        )
    if resp.status_code >= 400:
        raise IntegrationError(
            f"Slack returned HTTP {resp.status_code} for {method}: "
            f"{resp.text[:200]}",
            system=SYSTEM,
        )

    try:
        body = resp.json()
    except ValueError as exc:
        raise IntegrationError(
            f"Slack returned a non-JSON body for {method}", system=SYSTEM
        ) from exc

    if not body.get("ok"):
        raise IntegrationError(
            f"Slack rejected {method}: {body.get('error', 'unknown_error')}",
            system=SYSTEM,
            hint=_hint_for(body.get("error", "")),
        )
    return body


def _hint_for(error: str) -> Optional[str]:
    """Turn Slack's terse error slug into the next action to take."""
    return {
        "invalid_auth": "SLACK_BOT_TOKEN is not valid for this workspace.",
        "not_authed": "SLACK_BOT_TOKEN is empty or malformed.",
        "token_revoked": "The bot token has been revoked; reinstall the app.",
        "account_inactive": "The bot user or workspace has been deleted.",
        "missing_scope": "Add the chat:write scope and reinstall the app.",
        "channel_not_found": (
            "The channel does not exist, or the bot cannot see it. Set "
            "SLACK_DEFAULT_CHANNEL to a channel id the bot can reach."
        ),
        "not_in_channel": (
            "Invite the bot to the channel, or grant chat:write.public."
        ),
        "no_permission": "The bot is not a member of that conversation.",
        "is_archived": "That channel is archived.",
        "msg_too_long": "The message exceeds Slack's 40k-character limit.",
    }.get(error)


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def _normalise_channel(channel: str) -> str:
    """Strip a leading ``#``; Slack's API takes a bare name or an id."""
    return (channel or "").strip().lstrip("#")


def resolve_channel(requested: str) -> str:
    """Apply the channel policy, or raise if the request is not permitted."""
    requested = _normalise_channel(requested)

    if SLACK_DEFAULT_CHANNEL:
        return _normalise_channel(SLACK_DEFAULT_CHANNEL)

    if SLACK_CHANNEL_ALLOWLIST:
        allowed = {_normalise_channel(c) for c in SLACK_CHANNEL_ALLOWLIST}
        if requested not in allowed:
            raise IntegrationError(
                f"channel '{requested}' is not in SLACK_CHANNEL_ALLOWLIST",
                system=SYSTEM,
                hint=f"Allowed: {', '.join(sorted(allowed))}",
            )
    if not requested:
        raise IntegrationError("no channel given", system=SYSTEM)
    return requested


def _dedupe_key(channel: str, text: str) -> str:
    digest = hashlib.sha256(f"{channel}\n{text}".encode("utf-8")).hexdigest()
    return digest[:32]


def _read_ledger() -> Dict[str, Any]:
    """Load the sent-ledger, treating any unreadable file as empty.

    A corrupt ledger must not block the reporter: the cost of a lost dedupe
    record is one duplicate message, the cost of raising here is a failed run.
    """
    try:
        return json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_ledger(ledger: Dict[str, Any]) -> None:
    try:
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a crash mid-write cannot leave a truncated
        # ledger that silently disables dedupe on the next run.
        tmp = _LEDGER_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        tmp.replace(_LEDGER_PATH)
    except OSError as exc:
        logger.warning("could not persist the Slack dedupe ledger: %s", exc)


def _prune(ledger: Dict[str, Any], now: float) -> Dict[str, Any]:
    return {
        k: v
        for k, v in ledger.items()
        if isinstance(v, dict) and now - float(v.get("at", 0)) < SLACK_DEDUPE_TTL_S
    }


def _already_sent(key: str, now: float) -> Optional[Dict[str, Any]]:
    return _prune(_read_ledger(), now).get(key)


def _record_sent(key: str, channel: str, ts: str, now: float) -> None:
    ledger = _prune(_read_ledger(), now)
    ledger[key] = {"at": now, "channel": channel, "ts": ts}
    _write_ledger(ledger)


# ---------------------------------------------------------------------------
# Markdown -> Slack mrkdwn
# ---------------------------------------------------------------------------

# Code spans and fences keep their content; everything else is converted.
_CODE = re.compile(r"(```.*?```|`[^`\n]+`)", re.S)
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<![*\w])\*(?![\s*])(.+?)(?<![\s*])\*(?![*\w])")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*$", re.M)
_BULLET = re.compile(r"^(\s*)[-*+]\s+", re.M)


def _escape(text: str) -> str:
    # Slack treats &, < and > as control characters in message text.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _convert_prose(text: str) -> str:
    links: list[str] = []

    def stash(match: "re.Match[str]") -> str:
        links.append(f"<{match.group(2)}|{_escape(match.group(1))}>")
        return f"\x00{len(links) - 1}\x00"

    text = _LINK.sub(stash, text)
    text = _escape(text)
    text = _HEADING.sub(r"**\1**", text)
    text = _BULLET.sub(r"\1• ", text)
    text = _ITALIC.sub(r"_\1_", text)
    text = _BOLD.sub(lambda m: f"*{m.group(1) or m.group(2)}*", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], text)


def markdown_to_mrkdwn(text: str) -> str:
    """Render the reporter's Markdown in Slack's own markup.

    The model writes standard Markdown - it is what models write reliably,
    and what the dashboard renders - but Slack's ``mrkdwn`` is a different
    dialect: ``*bold*`` not ``**bold**``, ``<url|label>`` not
    ``[label](url)``, no headings. Converting at the edge keeps both views
    readable from one message.
    """
    # Code is set aside, not split around: bold often wraps a code span
    # ("**lag on `group`**"), and its markers sit on either side of it.
    code: list[str] = []

    def stash(match: "re.Match[str]") -> str:
        code.append(_escape(match.group(0)))
        return f"\x01{len(code) - 1}\x01"

    text = _convert_prose(_CODE.sub(stash, text))
    return re.sub(r"\x01(\d+)\x01", lambda m: code[int(m.group(1))], text)


# ---------------------------------------------------------------------------
# The one write
# ---------------------------------------------------------------------------


def post_message(channel: str, text: str) -> Dict[str, Any]:
    """Post to Slack, subject to the channel policy, dry run and dedupe.

    Returns the fixture back-end's ack shape (``ok`` / ``channel`` / ``ts``)
    plus whichever of ``dry_run`` / ``deduplicated`` applied, so the model can
    tell the difference between "posted", "would have posted" and "already
    posted" instead of reporting all three as success.
    """
    target = resolve_channel(channel)
    requested = _normalise_channel(channel)
    now = time.time()
    key = _dedupe_key(target, text)

    ack: Dict[str, Any] = {"ok": True, "channel": target}
    if requested and requested != target:
        # Say so rather than silently redirecting: an RCA that claims it was
        # posted to #sre-oncall when it went to #sre-sandbox is a small lie
        # the on-call human would have no way to catch.
        ack["requested_channel"] = requested
        ack["note"] = "channel overridden by SLACK_DEFAULT_CHANNEL"

    prior = _already_sent(key, now)
    if prior:
        return {
            **ack,
            "ts": prior.get("ts"),
            "deduplicated": True,
            "note": (
                "identical message already posted to this channel within the "
                "dedupe window; not posted again"
            ),
        }

    if SLACK_DRY_RUN:
        # Still hit the API, just not the writing part - this is what makes a
        # dry run evidence that live mode works rather than a no-op.
        auth = _call("auth.test")
        return {
            **ack,
            "ts": None,
            "dry_run": True,
            "authenticated_as": auth.get("user"),
            "team": auth.get("team"),
            "note": (
                "SLACK_DRY_RUN is on (the default in live mode) - the "
                "credential and workspace were verified but no message was "
                "posted. Set SLACK_DRY_RUN=false to actually post."
            ),
        }

    body = _call(
        "chat.postMessage",
        {"channel": target, "text": markdown_to_mrkdwn(text), "unfurl_links": False},
    )
    ts = body.get("ts")
    _record_sent(key, target, ts, now)
    # Slack answers with the channel id; keep the name too, so the model can
    # say where the message went.
    return {**ack, "channel": target, "channel_id": body.get("channel"), "ts": ts}
