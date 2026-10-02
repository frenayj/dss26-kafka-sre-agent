#!/usr/bin/env bash
# preflight.sh - verify everything is ready for a scenario of the Kafka SRE
# demo before you hit "run". Runs every check and exits non-zero if any
# failed, so you can stick it in front of any scenario target.
#
# Checks (in order):
#   1. .env present and the must-have vars set (ANTHROPIC_API_KEY,
#      ACCEPT_EULA=true).
#   2. docker compose services are running.
#   3. Lenses MCP / Schema Registry / Kafka Connect / LLM gateway HTTP
#      endpoints reachable.
#   4. .venv exists and build_model() returns a gateway-routed OpenAI client -
#      guards against a Strands SDK upgrade silently changing the wiring.
#
# Safe to run any time. Idempotent. ctrl-C anywhere.

set -euo pipefail

# ---------- locate repo + load .env ----------
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_ROOT="$( cd -- "${SCRIPT_DIR}/../.." &> /dev/null && pwd )"

if [[ -f "${REPO_ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a; source "${REPO_ROOT}/.env"; set +a
fi
# Opt-in parallel-port profile (see ports.parallel.sample) - overrides .env
# so this stack can run next to another Lenses/Kafka stack.
if [[ -f "${REPO_ROOT}/ports.parallel" ]]; then
  # shellcheck disable=SC1091
  set -a; source "${REPO_ROOT}/ports.parallel"; set +a
fi

# ---------- pretty printing ----------
bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }

PASS=0
FAIL=0
ok()  { green "  [ok]   $*"; PASS=$((PASS+1)); }
bad() { red   "  [FAIL] $*"; FAIL=$((FAIL+1)); }

cat <<'BANNER'
+============================================================+
|  PREFLIGHT  -  scenario readiness check                    |
+============================================================+
BANNER

# ---------- 1. .env + required vars ----------
bold "1. .env and required secrets"

if [[ ! -f "${REPO_ROOT}/.env" ]]; then
  bad ".env not found at ${REPO_ROOT}/.env (copy .env.sample and fill in)"
else
  ok ".env present"
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  bad "ANTHROPIC_API_KEY is empty"
else
  ok "ANTHROPIC_API_KEY set"
fi

if [[ "${ACCEPT_EULA:-}" != "true" ]]; then
  bad "ACCEPT_EULA is not true - Lenses HQ will not start until you accept the EULA"
else
  ok "ACCEPT_EULA=true"
fi

echo

# ---------- 2. docker compose services ----------
bold "2. docker compose services"

if ! command -v docker &> /dev/null; then
  bad "docker not on PATH"
elif ! docker compose version &> /dev/null; then
  bad "docker compose v2 not available"
else
  # `docker compose ps` returns 0 even if no services are running, so check
  # the count of running containers instead.
  RUNNING=$(docker compose --env-file "${REPO_ROOT}/.env" \
              -f "${REPO_ROOT}/harness/stack/docker-compose.yml" \
              ps --format json 2>/dev/null \
            | grep -c '"State":"running"' || true)
  if [[ "${RUNNING}" -eq 0 ]]; then
    bad "no compose services running - start with: make up"
  else
    ok "compose services running: ${RUNNING}"
  fi
fi

echo

# ---------- 3. HTTP endpoints ----------
bold "3. HTTP endpoints reachable"

check_url() {
  local label="$1" url="$2"
  if curl -sfm 3 -o /dev/null "${url}"; then
    ok "${label} reachable (${url})"
  else
    bad "${label} not reachable at ${url}"
  fi
}

# Lenses MCP serves JSON-RPC over POST at /mcp - GET returns 405 (Method Not
# Allowed). Use a presence-of-route probe: any 2xx/4xx response on /mcp proves
# the server is up; a connection failure (000) or 404 means it isn't.
check_mcp() {
  local label="$1" url="$2"
  local code
  code=$(curl -sm 3 -o /dev/null -w "%{http_code}" "${url}" || echo "000")
  if [[ "${code}" =~ ^[24] ]] || [[ "${code}" == "405" ]]; then
    ok "${label} reachable (${url}, HTTP ${code})"
  else
    bad "${label} not reachable at ${url} (HTTP ${code})"
  fi
}

check_mcp "Lenses MCP" "${LENSES_MCP_URL:-http://localhost:${HOST_PORT_MCP:-8000}}/mcp"
check_url "Schema Registry" "${SCHEMA_REGISTRY_PROD:-http://localhost:${HOST_PORT_SR_PROD:-8081}}/subjects"
check_url "Kafka Connect" "${CONNECT_PROD_URL:-http://localhost:${HOST_PORT_CONNECT_PROD:-8093}}/connectors"
check_url "LLM gateway" "http://localhost:${HOST_PORT_LLM_GATEWAY:-4000}/health/liveliness"

echo

# ---------- 4. stub data + venv + wire-level smoke ----------
bold "4. agent code + wire-level smoke"

GITHUB_SNAPSHOT="harness/stubs/data/github-dss26-org.json"
if [[ -f "${REPO_ROOT}/${GITHUB_SNAPSHOT}" ]]; then
  ok "GitHub stub snapshot present: ${GITHUB_SNAPSHOT}"
else
  bad "missing GitHub stub snapshot: ${GITHUB_SNAPSHOT} (python3 harness/github_org/snapshot.py)"
fi

VENV_PY="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "${VENV_PY}" ]]; then
  ok "no .venv - skipping the host-side wire check (only host runs need it: make venv)"
else
  ok ".venv/bin/python present"

  # Wire-level smoke: confirm build_model() returns an OpenAI-compatible
  # handle pointed at the gateway, and resolve_model() passes aliases through
  # / falls back to the per-role default. Catches the most likely silent
  # regression: a Strands SDK upgrade changing OpenAIModel's shape, or a
  # gateway-URL/alias mismatch.
  if "${VENV_PY}" - <<'PY' 2>/dev/null; then
import sys
from agent.config import LLM_GATEWAY_URL, resolve_model, SUPERVISOR_MODEL
from agent.models import build_model

# Alias pass-through + default fallback.
assert resolve_model("claude-haiku", SUPERVISOR_MODEL) == "claude-haiku"
assert resolve_model(None, SUPERVISOR_MODEL) == SUPERVISOR_MODEL

# build_model returns an OpenAI-compatible handle bound to the gateway.
m = build_model("claude")
cfg = getattr(m, "config", {})
ca = getattr(m, "client_args", {})
assert cfg.get("model_id") == "claude", cfg
assert ca.get("base_url") == LLM_GATEWAY_URL, ca
sys.exit(0)
PY
    ok "build_model() returns a gateway-routed OpenAI client (alias -> ${LLM_GATEWAY_URL:-http://localhost:4000/v1})"
  else
    bad "wire-level smoke failed - agent gateway wiring (agent.models/agent.config) changed"
    bad "  re-run manually: ${VENV_PY} -c 'from agent.models import build_model; print(build_model(\"claude\").config)'"
  fi
fi

echo

# ---------- summary ----------
hr() { printf -- "------------------------------------------------------------\n"; }
hr
if [[ "${FAIL}" -eq 0 ]]; then
  green "PREFLIGHT OK - ${PASS} checks passed."
  exit 0
else
  red   "PREFLIGHT FAILED - ${FAIL} check(s) failed, ${PASS} passed."
  exit 1
fi
