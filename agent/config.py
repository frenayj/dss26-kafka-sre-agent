"""Configuration for the Kafka SRE agent.

Loads ``.env`` once at import time and exposes the env-driven settings as
module-level constants with demo-friendly defaults. ``.env.sample`` documents
every variable.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths - anything that needs to resolve a file under the repo should derive
# from REPO_ROOT, never from cwd.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = REPO_ROOT / "agent"
SKILLS_DIR = AGENT_DIR / "skills"

# Load .env early so every downstream module reads the same values. No-op if
# .env doesn't exist (e.g. on CI).
load_dotenv(REPO_ROOT / ".env")

# The Lenses service-account key `make provision` writes for compose, so a
# host run (`make run`, `python -m agent.server`) uses it too.
load_dotenv(REPO_ROOT / "harness" / "stack" / "sa-credentials.conf")

# Opt-in parallel-port profile (see ports.parallel.sample): host-port and
# URL overrides that let this stack run next to another Lenses/Kafka stack.
# Loaded with override=True so it wins over .env. No-op when absent.
load_dotenv(REPO_ROOT / "ports.parallel", override=True)

# ---------------------------------------------------------------------------
# Models: every role names a gateway ALIAS, never a provider model id. The
# LiteLLM gateway maps each alias to a provider model in agent/gateway/litellm.yaml,
# so switching a role to another model is a dropdown in the UI or an env
# override here - never a code change.
# ---------------------------------------------------------------------------

SUPERVISOR_MODEL = os.environ.get("SUPERVISOR_MODEL", "claude")
DIAGNOSIS_MODEL = os.environ.get("DIAGNOSIS_MODEL", "claude")
TRIAGE_MODEL = os.environ.get("TRIAGE_MODEL", "claude")
FORENSICS_MODEL = os.environ.get("FORENSICS_MODEL", "claude")
REPORTER_MODEL = os.environ.get("REPORTER_MODEL", "claude")


def resolve_model(value: str | None, default: str) -> str:
    """The alias a run asked for, or the role's default when it named none.

    Any alias passes through untouched, so a role can use any alias defined
    in agent/gateway/litellm.yaml.
    """
    return value or default


# ---------------------------------------------------------------------------
# External endpoints.
# ---------------------------------------------------------------------------

LENSES_MCP_URL = os.environ.get("LENSES_MCP_URL", "http://localhost:8000")

# Lenses service-account token (harness/seed/provision_service_account.py). When set,
# the agent presents it as a static Bearer credential and SKIPS the interactive
# OAuth flow entirely - no browser, no ~1h expiry mid-run, and a fresh clone can
# be driven end to end by a script. Empty falls back to OAuth, which is still
# the right thing for a human exploring the MCP server by hand.
LENSES_API_KEY = os.environ.get("LENSES_API_KEY", "").strip()

# LiteLLM gateway. The default is its published port, for a host run; compose
# points the agent container at the in-network service. ``LLM_GATEWAY_API_KEY``
# is the gateway master key, defaulting to the same demo value as compose.
LLM_GATEWAY_URL = os.environ.get("LLM_GATEWAY_URL", "http://localhost:4000/v1")
LLM_GATEWAY_API_KEY = (
    os.environ.get("LLM_GATEWAY_API_KEY")
    or os.environ.get("LITELLM_MASTER_KEY")
    or "sk-kafka-sre-demo"
)

# ---------------------------------------------------------------------------
# Integration mode - simulated vs live back-ends.
#
# Each external system the agent talks to (PagerDuty / GitHub / Confluence /
# Slack) runs in one of two modes, chosen per server:
#
#   stub (default) - an offline test double from the harness
#     (``harness/stubs/``, the package named by STUB_MCP_PACKAGE). Fully
#     deterministic, no credentials, no egress.
#   live           - the real vendor: PagerDuty's and GitHub's own MCP
#     servers, or this agent's Confluence and Slack servers
#     (``agent/mcp_servers/``). Needs credentials.
#
# ``agent.mcp_clients`` picks the server from the mode at startup, so flipping
# a server is an env change and a restart - never a code change.
#
# Deliberately NOT a global switch: a broken or rate-limited upstream should
# cost you one sub-agent's tool list, not the whole run.
# ---------------------------------------------------------------------------

def resolve_integration_mode(name: str) -> str:
    """``live`` if ``<NAME>_MODE`` says so, otherwise ``stub``.

    Anything else (a typo included) means ``stub``: it should degrade to the
    safe, offline back-end, not take the stack down on boot.
    """
    raw = os.environ.get(f"{name.upper()}_MODE", "stub").strip().lower()
    return "live" if raw == "live" else "stub"


# Where stub mode finds its test doubles. The agent never imports them: it
# spawns ``python -m <package>.<name>_mcp`` like any other stdio server.
STUB_MCP_PACKAGE = os.getenv("STUB_MCP_PACKAGE", "harness.stubs")

PAGERDUTY_MODE = resolve_integration_mode("pagerduty")
GITHUB_MODE = resolve_integration_mode("github")
CONFLUENCE_MODE = resolve_integration_mode("confluence")
SLACK_MODE = resolve_integration_mode("slack")

# --- PagerDuty (live mode only) --------------------------------------------
# A User API Token (My Profile -> User Settings -> Create API User Token), sent
# as ``Token token=``. It serves two callers: PagerDuty's hosted MCP server,
# which gives the agent its PagerDuty tools and expects a user token (writes
# land in the incident timeline under that user's name), and the agent
# server's incident poller, which reads the REST API directly.
PAGERDUTY_API_KEY = os.environ.get("PAGERDUTY_API_KEY", "").strip()
PAGERDUTY_API_URL = os.environ.get(
    "PAGERDUTY_API_URL", "https://api.pagerduty.com"
).rstrip("/")
# PagerDuty's hosted MCP server. EU accounts: https://mcp.eu.pagerduty.com/mcp
PAGERDUTY_MCP_URL = os.environ.get(
    "PAGERDUTY_MCP_URL", "https://mcp.pagerduty.com/mcp"
).rstrip("/")
# Optional filter: restrict the poller to one or more PD service ids
# (comma-separated). Without it, every open incident on the account reaches the
# dashboard - and is auto-run.
PAGERDUTY_SERVICE_IDS: tuple[str, ...] = tuple(
    s.strip()
    for s in os.environ.get("PAGERDUTY_SERVICE_IDS", "").split(",")
    if s.strip()
)


def _poll_interval(raw: str) -> float:
    """Seconds between PagerDuty polls; a typo means the default, not a crash."""
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 5.0


# How often the agent server checks PagerDuty for new incidents in live mode.
# 0 turns the poller off (the dashboard then shows no live incidents).
PAGERDUTY_POLL_S = _poll_interval(os.environ.get("PAGERDUTY_POLL_S", "5"))


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var, tolerating the spellings people actually use."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_csv(name: str) -> tuple[str, ...]:
    return tuple(s.strip() for s in os.environ.get(name, "").split(",") if s.strip())


# --- Slack (live mode only) -------------------------------------------------
# A bot token (``xoxb-...``) with the ``chat:write`` scope. ``chat:write.public``
# additionally lets the bot post to public channels it has not been invited to.
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "").strip()
SLACK_API_URL = os.environ.get("SLACK_API_URL", "https://slack.com/api").rstrip("/")

# Dry run DEFAULTS ON in live mode, and that is deliberate.
#
# Posting to Slack is the first genuinely irreversible thing this agent does:
# it notifies humans in a real channel, and there is no undo that un-pings
# anyone. So going live is two deliberate steps - point at the workspace, then
# arm it - rather than one env var.
#
# In dry-run the credential and workspace are validated against the real API
# (via ``auth.test``), so it still proves the integration works; only
# ``chat.postMessage`` is withheld. The channel is not checked until a real
# post - ``auth.test`` cannot see it.
SLACK_DRY_RUN = _env_bool("SLACK_DRY_RUN", True)

# Channel policy, most specific first:
#   SLACK_DEFAULT_CHANNEL  - pin every post here, overriding whatever channel
#     the model asks for. Both a guardrail and the practical fix for prompts
#     that hardcode ``#sre-oncall``, which will not exist in most workspaces.
#   SLACK_CHANNEL_ALLOWLIST - if set, the model may choose, but only from here.
#   neither                - the model's channel is used as-is.
SLACK_DEFAULT_CHANNEL = os.environ.get("SLACK_DEFAULT_CHANNEL", "").strip()
SLACK_CHANNEL_ALLOWLIST: tuple[str, ...] = _env_csv("SLACK_CHANNEL_ALLOWLIST")

# How long an identical (channel, text) post is suppressed as a duplicate.
# Sized for "one incident, one run, however many retries that took" - the
# agentic loop and the gateway both retry, and each retry re-runs the reporter.
SLACK_DEDUPE_TTL_S = int(os.environ.get("SLACK_DEDUPE_TTL_S", "86400"))

# Where the dedupe ledger is persisted. Compose points it at the agent-data
# volume: a ledger that dies with the container never fires, because retries
# after a restart are exactly when it is needed.
SLACK_LEDGER_PATH = Path(
    os.environ.get("SLACK_LEDGER_PATH", str(REPO_ROOT / "logs" / "slack_sent.json"))
)

# --- GitHub -----------------------------------------------------------------
# Live mode runs GitHub's official MCP server (github/github-mcp-server) over
# stdio, read-only and limited to the tools forensics needs to find a change
# on its own: org-wide PR and code search, PR/commit/file reads. Stub mode
# serves the same tool names from a snapshot of the same org.
#
# The token needs read access to the org's repos: a fine-grained PAT with
# "Contents: read" and "Pull requests: read" (+ "Metadata: read", which GitHub
# adds automatically), or "Actions: read" too if you add the actions tools.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
# Point at a GitHub Enterprise Server instance with e.g.
# ``https://github.example.com/api/v3``.
GITHUB_API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")

# The organisation the bank's code lives in. It is the only GitHub fact the
# agent is given - which repo, PR or commit caused an incident is for it to
# find. Override to point the demo at your own copy of the org.
GITHUB_ORG = os.environ.get("GITHUB_ORG", "").strip() or "dss26-org"

# Hard cap on forensics' GitHub calls per invocation (see agent/tool_budget.py).
# The prompt asks for about eight; the cap stops a run that cannot find its
# culprit from browsing the org for ten minutes. 0 disables it.
FORENSICS_TOOL_BUDGET = int(os.environ.get("FORENSICS_TOOL_BUDGET", "") or 14)

# How to start the official server: the binary on PATH (baked into the agent
# image), or e.g. ``docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN
# ghcr.io/github/github-mcp-server`` on a host without it.
GITHUB_MCP_COMMAND = os.environ.get("GITHUB_MCP_COMMAND", "").strip() or "github-mcp-server"
# A small, read-only tool surface: a model choosing between 8 tools picks
# better than one choosing between 80, and none of these can change anything.
GITHUB_MCP_TOOLS: tuple[str, ...] = _env_csv("GITHUB_MCP_TOOLS") or (
    "search_pull_requests",
    "list_pull_requests",
    "pull_request_read",
    "search_code",
    "get_file_contents",
    "list_commits",
    "get_commit",
    "search_repositories",
)

# --- Confluence (live mode only) --------------------------------------------
# Confluence Cloud, REST API v2. CONFLUENCE_BASE_URL is the site's wiki root,
# e.g. ``https://your-site.atlassian.net/wiki``. Auth is HTTP basic with the
# account's email and an API token (id.atlassian.com → Security → API tokens).
CONFLUENCE_BASE_URL = os.environ.get("CONFLUENCE_BASE_URL", "").strip().rstrip("/")
CONFLUENCE_EMAIL = os.environ.get("CONFLUENCE_EMAIL", "").strip()
CONFLUENCE_API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN", "").strip()

# Space policy, same shape as Slack's channel policy: CONFLUENCE_SPACE pins
# every page to one space KEY, overriding the ``SRE`` the reporter prompt
# hardcodes (which may not exist on your site). Blank = use the model's space.
# It also scopes the knowledge-base search; blank = every space the account
# can read.
CONFLUENCE_SPACE = os.environ.get("CONFLUENCE_SPACE", "").strip()
# Optional: file every RCA under one parent page instead of the space root.
CONFLUENCE_PARENT_PAGE_ID = os.environ.get("CONFLUENCE_PARENT_PAGE_ID", "").strip()

# Dry run DEFAULTS ON in live mode, for the same reason as SLACK_DRY_RUN:
# publishing a page into a shared space notifies its watchers, so going live
# is two deliberate steps. A dry run still authenticates and resolves the
# space against the real API; only the page creation is withheld.
CONFLUENCE_DRY_RUN = _env_bool("CONFLUENCE_DRY_RUN", True)
