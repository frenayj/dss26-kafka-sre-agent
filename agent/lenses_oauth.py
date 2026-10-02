"""OAuth 2.1 client wiring for talking to Lenses MCP.

Lenses MCP enforces OAuth (RFC 7662 introspection against Lenses HQ) when
``OAUTH_ENABLED=true`` (the upstream default). The MCP Python SDK ships an
``OAuthClientProvider`` that runs the full PKCE-based flow + Dynamic Client
Registration; we just have to plug in:

  * a ``TokenStorage`` so we don't re-auth every demo run,
  * a ``redirect_handler`` that PRINTS the authorize URL (instead of the
    default behaviour, which silently opens a browser tab),
  * a ``callback_handler`` that runs a tiny localhost HTTP server to
    receive the redirect after the user logs in.

Tokens are cached at ``~/.cache/kafka-sre-agent/oauth.json``. Delete that
file if you want to force a fresh login.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx
from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.oauth2 import TokenStorage
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from rich.console import Console

logger = logging.getLogger(__name__)

# Port the localhost callback server listens on. Must match the redirect_uri
# we register with Lenses HQ via DCR. 8765 is free on most dev machines.
CALLBACK_PORT = int(os.environ.get("LENSES_OAUTH_CALLBACK_PORT", "8765"))
# Interface the callback server binds. 127.0.0.1 on the host (default); inside
# a container set LENSES_OAUTH_CALLBACK_HOST=0.0.0.0 so Docker's published
# 8765 reaches it. The redirect_uri stays ``localhost`` either way - that's
# what the operator's browser resolves.
CALLBACK_BIND_HOST = os.environ.get("LENSES_OAUTH_CALLBACK_HOST", "127.0.0.1")
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "kafka-sre-agent"
TOKEN_FILE = CACHE_DIR / "oauth.json"


# Module-level state for surfacing the pending authorize URL to the React UI
# while uvicorn is still blocked on the lifespan that started the OAuth flow.
# Set in print_redirect_handler, served by the temporary /ping handler, and
# cleared in localhost_callback_handler once the user completes (or aborts).
_auth_url_lock = threading.Lock()
_pending_auth_url: Optional[str] = None


def _set_pending_auth_url(url: Optional[str]) -> None:
    global _pending_auth_url
    with _auth_url_lock:
        _pending_auth_url = url


def _get_pending_auth_url() -> Optional[str]:
    with _auth_url_lock:
        return _pending_auth_url


class FileTokenStorage(TokenStorage):
    """Persist OAuth tokens + DCR client info to a single JSON file.

    One file holds both the access/refresh token bundle and the registered
    client info; the MCP SDK queries them separately. Reading and writing is
    deliberately synchronous - the cost of a few-KB JSON read/write is far
    below any network call we'd otherwise make on every request.
    """

    def __init__(self, path: Path = TOKEN_FILE) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except Exception:
            return {}

    def _write(self, blob: dict) -> None:
        self._path.write_text(json.dumps(blob, indent=2))
        # tokens are sensitive - restrict to user only
        try:
            self._path.chmod(0o600)
        except OSError:
            pass

    async def get_tokens(self) -> Optional[OAuthToken]:
        blob = self._read().get("tokens")
        if not blob:
            return None
        try:
            return OAuthToken(**blob)
        except Exception:
            return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        blob = self._read()
        blob["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self._write(blob)

    async def get_client_info(self) -> Optional[OAuthClientInformationFull]:
        blob = self._read().get("client_info")
        if not blob:
            return None
        try:
            return OAuthClientInformationFull(**blob)
        except Exception:
            return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        blob = self._read()
        blob["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
        self._write(blob)


# ---------------------------------------------------------------------------
# Redirect handler: prints the authorize URL prominently.
# ---------------------------------------------------------------------------

_console = Console()


async def print_redirect_handler(authorize_url: str) -> None:
    """Show the user the authorize URL.

    The URL is printed on its own line with no decoration so a triple-click
    selects it cleanly. Wrapping it inside a Rich Panel injected box-drawing
    border characters into the URL when the terminal width was narrower than
    the URL, which broke the redirect_uri / code_challenge query params on
    copy-paste.

    The URL is also stashed in module state so the temporary /ping handler
    can surface it to the React UI - see ``_make_handler`` below.
    """
    _set_pending_auth_url(authorize_url)
    _console.print()
    _console.print(
        "[bold yellow]🔐  Lenses MCP requires OAuth login[/bold yellow]"
    )
    _console.print(
        "    Sign in with your Lenses HQ credentials "
        "(default: [cyan]admin / admin[/cyan]).",
    )
    _console.print(
        f"    You'll be redirected back to [cyan]{REDIRECT_URI}[/cyan] when done."
    )
    _console.print()
    _console.print("    [bold]Open this URL in your browser:[/bold]")
    _console.print()
    # Bare URL - no wrapping, no markup, no panel borders. Triple-click safe.
    _console.print(authorize_url, soft_wrap=True, no_wrap=True, overflow="ignore", highlight=False)
    _console.print()


# ---------------------------------------------------------------------------
# Callback handler: runs a one-shot localhost HTTP server, returns (code, state).
# ---------------------------------------------------------------------------


class _CallbackCapture:
    """Mutable holder so the HTTP handler can stash code + state for us."""

    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


def _make_handler(capture: _CallbackCapture, done: threading.Event):
    class _Handler(BaseHTTPRequestHandler):
        # Silence the default access log - keeps the demo terminal clean.
        def log_message(self, fmt: str, *args) -> None:  # noqa: ARG002
            return

        def do_OPTIONS(self):  # noqa: N802
            # CORS preflight from the React dev server on :5173.
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)

            # /ping during the OAuth-blocked window: surface the auth URL to
            # the React UI so it can show a "Sign in to Lenses" dialog rather
            # than a bare red "agent offline" dot.
            if parsed.path == "/ping":
                payload = {
                    "status": "needs_auth",
                    "auth_url": _get_pending_auth_url(),
                    "tools": {},
                }
                body_bytes = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                self.wfile.write(body_bytes)
                return

            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed.query)
            capture.code = (params.get("code") or [None])[0]
            capture.state = (params.get("state") or [None])[0]
            capture.error = (params.get("error") or [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if capture.error:
                body = f"<h1>OAuth error</h1><pre>{capture.error}</pre>"
            else:
                body = (
                    "<!doctype html><html><head><title>Authenticated</title></head>"
                    "<body style='font-family:sans-serif;max-width:480px;margin:48px auto;'>"
                    "<h1>✅ Authenticated</h1>"
                    "<p>You can close this tab and return to the terminal.</p>"
                    "</body></html>"
                )
            self.wfile.write(body.encode())
            done.set()

    return _Handler


async def localhost_callback_handler() -> tuple[str, Optional[str]]:
    """Block until Lenses HQ redirects to ``/callback`` with the auth code.

    Runs the HTTP server in a background thread so we don't fight the
    asyncio event loop the MCP SDK is already running. The current task
    parks on the ``done`` event with a small sleep loop.
    """
    capture = _CallbackCapture()
    done = threading.Event()
    server = HTTPServer((CALLBACK_BIND_HOST, CALLBACK_PORT), _make_handler(capture, done))

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Poll instead of blocking on Event so other tasks can still run.
        while not done.is_set():
            await asyncio.sleep(0.1)
    finally:
        server.shutdown()
        server.server_close()
        # Clear the URL so a subsequent fresh start doesn't leak stale state.
        _set_pending_auth_url(None)

    if capture.error:
        raise RuntimeError(f"OAuth error from authorization server: {capture.error}")
    if not capture.code:
        raise RuntimeError("OAuth callback received without an authorization code")
    return capture.code, capture.state


# ---------------------------------------------------------------------------
# Public factory.
# ---------------------------------------------------------------------------


def _hq_url() -> str:
    return (
        os.environ.get("LENSES_HQ_URL")
        or os.environ.get("LENSES_ADVERTISED_URL")
        or "http://localhost:9991"
    ).rstrip("/")


# ---------------------------------------------------------------------------
# Host remap - lets a containerized agent reach lenses-hq / lenses-mcp.
#
# Lenses MCP advertises ``localhost:9991`` (HQ) / ``localhost:8000`` (MCP) so
# the operator's browser can complete the OAuth login. But the agent's OWN
# server-side calls (DCR, token exchange, the MCP transport) can't reach
# ``localhost`` from inside a container. This transport rewrites the
# connection target for configured host:port pairs while leaving the request's
# Host header - and the browser-facing authorize URL / RFC 8707 resource
# string - untouched, so issuer/audience checks still see ``localhost``.
#
# Configure via LENSES_INTERNAL_REMAP="localhost:9991=lenses-hq:9991,...".
# Unset (host runs) → no remap, default factory, behavior unchanged.
# ---------------------------------------------------------------------------


def _parse_remap(spec: str) -> dict[tuple[str, int], tuple[str, int]]:
    remap: dict[tuple[str, int], tuple[str, int]] = {}
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        src, dst = (p.strip() for p in pair.split("=", 1))
        try:
            sh, sp = src.rsplit(":", 1)
            dh, dp = dst.rsplit(":", 1)
            remap[(sh, int(sp))] = (dh, int(dp))
        except ValueError:
            logger.warning("Ignoring malformed LENSES_INTERNAL_REMAP entry: %r", pair)
    return remap


class _RemapTransport(httpx.AsyncHTTPTransport):
    """Redirect outbound requests for specific host:port pairs to internal
    targets, preserving the original Host header (set by httpx before the
    request reaches the transport, so we only retarget the TCP connection)."""

    def __init__(self, remap: dict[tuple[str, int], tuple[str, int]], **kwargs):
        super().__init__(**kwargs)
        self._remap = remap

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        target = self._remap.get((request.url.host, port))
        if target:
            request.url = request.url.copy_with(host=target[0], port=target[1])
        return await super().handle_async_request(request)


def make_remap_client_factory():
    """Return an ``McpHttpClientFactory`` applying LENSES_INTERNAL_REMAP, or
    ``None`` when no remap is configured (so host runs keep the SDK default)."""
    spec = os.environ.get("LENSES_INTERNAL_REMAP", "").strip()
    remap = _parse_remap(spec) if spec else {}
    if not remap:
        return None

    logger.info("Lenses OAuth host remap active: %s", remap)

    def factory(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=True,
            headers=headers,
            timeout=timeout if timeout is not None else httpx.Timeout(30.0, read=300.0),
            auth=auth,
            transport=_RemapTransport(remap),
        )

    return factory


def _invalidate_stale_cache_if_needed() -> None:
    """If the cached OAuth state is no longer valid in Lenses HQ, wipe it.

    Lenses HQ stores DCR registrations and tokens in its postgres DB. Every
    ``docker compose down -v`` (license swap, infra refactor, etc.) wipes
    them - but our local cache at ``~/.cache/kafka-sre-agent/oauth.json``
    still has the old client_id and token. Without this check the OAuth
    provider would reuse the stale state, the user would sign in to HQ, and
    HQ would return ``HTTP 404 - App not found`` on the consent screen.
    Historically the #1 first-run pitfall.

    Detection strategy: hit ``/oauth2/introspect`` with the cached
    access_token (HQ has ``unauthenticatedIntrospection: true``, so we can
    call it without auth). If the response says ``active: false``, the
    cached state is dead - wipe both the token and the client_info so the
    next run does a fresh DCR + auth flow.

    If HQ is unreachable we keep the cache untouched (HQ might come up
    moments later) - safe-by-default.
    """
    if not TOKEN_FILE.exists():
        return

    try:
        blob = json.loads(TOKEN_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return

    tokens = blob.get("tokens") or {}
    access_token = tokens.get("access_token")
    cached_cid = (blob.get("client_info") or {}).get("client_id")

    # Nothing useful cached → nothing to invalidate.
    if not access_token and not cached_cid:
        return

    # If we don't have an access_token we can't introspect. Be conservative
    # and keep the cache; the first authorize call will surface the failure
    # and the user can clear manually. Most runs DO have a token because
    # OAuth completed at least once.
    if not access_token:
        return

    introspect_url = f"{_hq_url()}/oauth2/introspect"
    try:
        resp = httpx.post(
            introspect_url,
            data={"token": access_token, "token_type_hint": "access_token"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=3.0,
        )
    except httpx.HTTPError as exc:
        logger.debug("OAuth cache validation skipped (HQ unreachable: %s)", exc)
        return

    if resp.status_code != 200:
        # HQ rejected introspection - best-effort, leave cache alone.
        return

    try:
        data = resp.json()
    except ValueError:
        return

    if data.get("active") is True:
        return  # cache is still good

    logger.warning(
        "Cached OAuth state is no longer valid (HQ wiped or token revoked) - "
        "deleting %s so the next run does a fresh DCR + login.",
        TOKEN_FILE,
    )
    try:
        TOKEN_FILE.unlink()
    except OSError as exc:
        logger.warning("Failed to wipe stale OAuth cache: %s", exc)


def make_oauth_provider(server_url: str) -> OAuthClientProvider:
    """Build an ``OAuthClientProvider`` ready to plug into ``streamablehttp_client``.

    Side effect: invalidates the local OAuth cache if Lenses HQ no longer
    knows about our cached client_id (e.g. after a ``docker compose down -v``).
    Without this, the agent reuses the stale registration and the user hits
    "App not found" on the consent screen.
    """
    _invalidate_stale_cache_if_needed()

    metadata = OAuthClientMetadata(
        redirect_uris=[REDIRECT_URI],  # type: ignore[arg-type]  (pydantic coerces str → AnyUrl)
        client_name="Kafka SRE Agent (demo)",
        scope="read write delete",
        token_endpoint_auth_method="none",  # public client + PKCE
    )
    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=metadata,
        storage=FileTokenStorage(),
        redirect_handler=print_redirect_handler,
        callback_handler=localhost_callback_handler,
    )
