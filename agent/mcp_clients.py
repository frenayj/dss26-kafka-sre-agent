"""MCP client factories: which server each integration talks to.

Every integration is either ``stub`` (an offline test double from the harness)
or ``live`` (``<NAME>_MODE``, see :mod:`agent.config`):

    Integration  live                                             stub
    PagerDuty    PagerDuty's hosted MCP server (Streamable HTTP)  harness.stubs.pagerduty_mcp
    GitHub       GitHub's github-mcp-server (stdio)               harness.stubs.github_mcp
    Confluence   agent.mcp_servers.confluence (stdio)             harness.stubs.confluence_mcp
    Slack        agent.mcp_servers.slack (stdio)                  harness.stubs.slack_mcp
    Lenses       the Lenses MCP server (Streamable HTTP), always

The stdio servers are child processes launched with ``python -m <module>``, so
they pick up the repo's virtualenv and ``PYTHONPATH``. The agent never imports
a test double: stub mode only changes which module is spawned (the package is
``STUB_MCP_PACKAGE``, ``harness.stubs`` by default).

Lenses MCP is a long-running container, authenticated with the provisioned
service-account key (``LENSES_API_KEY``) or, without one, an interactive OAuth
login against Lenses HQ.
"""

from __future__ import annotations

import os
import sys

import httpx
from mcp import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

from agent.config import (
    CONFLUENCE_MODE,
    GITHUB_API_URL,
    GITHUB_MCP_COMMAND,
    GITHUB_MCP_TOOLS,
    GITHUB_MODE,
    GITHUB_ORG,
    GITHUB_TOKEN,
    LENSES_API_KEY,
    LENSES_MCP_URL,
    PAGERDUTY_API_KEY,
    PAGERDUTY_MCP_URL,
    PAGERDUTY_MODE,
    REPO_ROOT,
    SLACK_MODE,
    STUB_MCP_PACKAGE,
)


def _stdio_params(module: str) -> StdioServerParameters:
    """Spawn ``python -m <module>`` from the repo root.

    The child inherits the parent environment, which is how the credential
    variables reach the live servers.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", module],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


def _stub(name: str) -> MCPClient:
    """The harness's offline test double for ``name``."""
    return MCPClient(lambda: stdio_client(_stdio_params(f"{STUB_MCP_PACKAGE}.{name}_mcp")))


# The only PagerDuty tools the agent sees in live mode. The hosted server
# exposes 18 - schedules, services, status pages, orchestrations - and a user
# token can write to all of them. Triage and the reporter need the incident
# pair and nothing else; every tool left out is one the model cannot misuse.
# Within this pair, :mod:`agent.pagerduty_guard` narrows the writes further.
PAGERDUTY_LIVE_TOOLS = ("browse_incidents", "manage_incidents")


def make_pagerduty_client() -> MCPClient:
    """PagerDuty's own hosted MCP server in live mode, the fixture stub otherwise.

    Unlike GitHub / Confluence / Slack, live PagerDuty does not go through our
    stub: the agent talks to the real vendor MCP server, with the vendor's tool
    names and schemas, so the prompts branch on the mode (see triage.md).
    """
    if PAGERDUTY_MODE != "live":
        return _stub("pagerduty")

    if not PAGERDUTY_API_KEY:
        raise RuntimeError(
            "PAGERDUTY_MODE=live needs PAGERDUTY_API_KEY (a PagerDuty User API "
            "Token), or set PAGERDUTY_MODE=stub to use the bundled incidents."
        )

    def _connect():
        return streamablehttp_client(
            PAGERDUTY_MCP_URL,
            headers={"Authorization": f"Token token={PAGERDUTY_API_KEY}"},
        )

    return MCPClient(
        _connect, tool_filters={"allowed": list(PAGERDUTY_LIVE_TOOLS)}
    )


def _github_official_params() -> StdioServerParameters:
    """GitHub's official MCP server (github/github-mcp-server) over stdio.

    ``--read-only`` drops every write tool before ``--tools`` narrows the rest
    to the forensics allowlist, so even a token with write scopes cannot be
    used to change the org. The child gets a minimal environment - the token
    goes in under the name the server reads, and nothing else of ours leaks
    into a third-party process.
    """
    command, *prefix = GITHUB_MCP_COMMAND.split()
    args = [*prefix, "stdio", "--read-only", "--tools", ",".join(GITHUB_MCP_TOOLS)]
    if not GITHUB_API_URL.startswith("https://api.github.com"):
        # GitHub Enterprise Server: https://ghe.example.com/api/v3 -> https://ghe.example.com
        args += ["--gh-host", GITHUB_API_URL.removesuffix("/api/v3")]
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN,
    }
    return StdioServerParameters(command=command, args=args, env=env)


def make_github_client() -> MCPClient:
    """GitHub's official MCP server in live mode, the snapshot stub otherwise.

    Both expose the same tool names and argument shapes (the stub mirrors the
    official server), so forensics' prompt and the UI renderers do not branch
    on the mode.
    """
    if GITHUB_MODE != "live":
        return _stub("github")
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "GITHUB_MODE=live needs GITHUB_TOKEN (read access to the "
            f"{GITHUB_ORG} repos), or set GITHUB_MODE=stub to use the snapshot."
        )
    return MCPClient(lambda: stdio_client(_github_official_params()), startup_timeout=60)


def make_confluence_client() -> MCPClient:
    """This agent's Confluence server in live mode, the knowledge-base stub otherwise."""
    if CONFLUENCE_MODE != "live":
        return _stub("confluence")
    return MCPClient(lambda: stdio_client(_stdio_params("agent.mcp_servers.confluence")))


def make_slack_client() -> MCPClient:
    """This agent's Slack server in live mode, the log-only stub otherwise."""
    if SLACK_MODE != "live":
        return _stub("slack")
    return MCPClient(lambda: stdio_client(_stdio_params("agent.mcp_servers.slack")))


class _StaticBearerAuth(httpx.Auth):
    """Sends a fixed ``Authorization: Bearer <token>`` header on every request."""

    def __init__(self, token: str) -> None:
        self._header_value = f"Bearer {token}"

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = self._header_value
        yield request


def make_lenses_client() -> MCPClient:
    """Connect to the Lenses MCP server over Streamable HTTP.

    With ``LENSES_API_KEY`` set (``make provision`` writes one for compose),
    the agent presents the service-account key and never prompts. Without it,
    the MCP SDK's OAuth provider runs an interactive login against Lenses HQ,
    printing the authorize URL rather than silently opening a browser (see
    :mod:`agent.lenses_oauth`).
    """
    from agent.lenses_oauth import make_oauth_provider, make_remap_client_factory

    url = LENSES_MCP_URL.rstrip("/")
    if not url.endswith("/mcp"):
        url += "/mcp"

    auth = _StaticBearerAuth(LENSES_API_KEY) if LENSES_API_KEY else make_oauth_provider(server_url=url)

    # In a container, LENSES_INTERNAL_REMAP retargets the server-side calls
    # from the advertised ``localhost`` URLs to the compose service names.
    # ``None`` on the host means the SDK default.
    remap_factory = make_remap_client_factory()

    def _connect():
        if remap_factory is not None:
            return streamablehttp_client(url, auth=auth, httpx_client_factory=remap_factory)
        return streamablehttp_client(url, auth=auth)

    # An OAuth login waits for a human in a browser, so give it ten minutes.
    return MCPClient(_connect, startup_timeout=60 if LENSES_API_KEY else 600)
