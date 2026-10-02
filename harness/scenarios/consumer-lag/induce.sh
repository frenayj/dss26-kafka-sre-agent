#!/usr/bin/env bash
# induce_lag.sh - deploy an INCOMPATIBLE Avro schema to the cards-prod-euw1
# Schema Registry. The fraud-decisioning engine (which was built against the
# v1 schema) will fail to deserialize new records and consumer-group lag will
# start growing within ~30s.
#
# Idempotent: running twice is harmless. Safe to ctrl-C anywhere.

set -euo pipefail

# ---------- locate repo + load .env ----------
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_ROOT="$( cd -- "${SCRIPT_DIR}/../../.." &> /dev/null && pwd )"

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

# ---------- config ----------
SR_PROD="${SCHEMA_REGISTRY_PROD:-http://localhost:${HOST_PORT_SR_PROD:-8081}}"
SUBJECT="cards.authorisation.requested.v1-value"
SCHEMAS_DIR="${REPO_ROOT}/harness/stack/schemas"
ORIG_SCHEMA="${SCHEMAS_DIR}/cards_authorisation_requested_v1.avsc"
BREAKING_SCHEMA="${SCHEMAS_DIR}/cards_authorisation_requested_v1_breaking.avsc"
SR_HEADER='Content-Type: application/vnd.schemaregistry.v1+json'

# Prefer the repo venv; the GitHub helpers are stdlib-only.
PY="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PY}" ]] || PY="python3"
# shellcheck source=github_org/lib.sh
source "${REPO_ROOT}/harness/github_org/lib.sh"

# ---------- banner ----------
cat <<'BANNER'
+================================================================+
|  INDUCE LAG  -  incompatible schema deployment                 |
|  subject: cards.authorisation.requested.v1-value               |
|  target:  cards-prod-euw1                                      |
+================================================================+
BANNER

echo "[induce_lag] target schema registry: ${SR_PROD}"
echo

# ---------- 1. reachability ----------
echo "[induce_lag] step 1/6: verifying prod Schema Registry is reachable..."
if ! curl --silent --show-error --fail --max-time 5 "${SR_PROD}/subjects" >/dev/null; then
  echo "[induce_lag] ERROR: cannot reach prod Schema Registry at ${SR_PROD}" >&2
  echo "[induce_lag] is the docker stack up?  ->  make up" >&2
  exit 1
fi
echo "[induce_lag] ok - SR is reachable"
echo

# ---------- 2. ensure original schema present ----------
echo "[induce_lag] step 2/6: ensuring original schema is registered (idempotent)..."
if [[ ! -f "${ORIG_SCHEMA}" ]]; then
  echo "[induce_lag] ERROR: original schema not found at ${ORIG_SCHEMA}" >&2
  exit 1
fi

# Wrap raw .avsc as the SR registration payload: {"schema":"<stringified avsc>"}
orig_payload=$(python3 -c 'import json, sys; print(json.dumps({"schema": sys.stdin.read()}))' < "${ORIG_SCHEMA}")
register_orig=$(curl --silent --show-error \
  -X POST \
  -H "${SR_HEADER}" \
  --data "${orig_payload}" \
  "${SR_PROD}/subjects/${SUBJECT}/versions" || true)
echo "[induce_lag] register-original response: ${register_orig}"
echo

# ---------- 3+4. ship the producer change ----------
# With GitHub live the change is a real merchant-gateway pull request: merge
# it, then run its release pipeline (gitops.py), which sets the subject's
# compatibility and registers the schema exactly as main now declares them.
# Without GitHub - or if it is unreachable - apply the same change from the
# local schema files below.
shipped_from_git=0
if gh_scenario_enabled; then
  echo "[induce_lag] step 3/6: merging the merchant-gateway change on GitHub (dss26-org)..."
  if gh_run induce_lag scenario.py culprit consumer-lag \
     && echo "[induce_lag] step 4/6: release pipeline - compatibility + schema from main..." \
     && gh_run induce_lag gitops.py schema --env prod; then
    shipped_from_git=1
  else
    echo "[induce_lag] WARN: GitHub path failed - applying the local schema files instead" >&2
  fi
  echo
fi

if [[ "${shipped_from_git}" != 1 ]]; then
# ---------- 3. relax compatibility ----------
echo "[induce_lag] step 3/6: setting subject compatibility to NONE so the breaking schema is accepted..."
curl --silent --show-error \
  -X PUT \
  -H "${SR_HEADER}" \
  --data '{"compatibility":"NONE"}' \
  "${SR_PROD}/config/${SUBJECT}" \
  | sed 's/^/[induce_lag]   sr> /'
echo

# ---------- 4. register the breaking schema ----------
echo "[induce_lag] step 4/6: registering the INCOMPATIBLE schema as a new version..."
if [[ ! -f "${BREAKING_SCHEMA}" ]]; then
  echo "[induce_lag] ERROR: breaking schema not found at ${BREAKING_SCHEMA}" >&2
  exit 1
fi

# Strip the doc-only "_comment_break" key - Avro will reject unknown top-level fields.
breaking_payload=$(python3 -c '
import json, sys
schema = json.load(sys.stdin)
schema.pop("_comment_break", None)
print(json.dumps({"schema": json.dumps(schema, indent=2, ensure_ascii=False)}))
' < "${BREAKING_SCHEMA}")

register_breaking=$(curl --silent --show-error \
  -X POST \
  -H "${SR_HEADER}" \
  --data "${breaking_payload}" \
  "${SR_PROD}/subjects/${SUBJECT}/versions")
echo "[induce_lag] register-breaking response: ${register_breaking}"
echo
fi

# ---------- 5. inject poison records under the breaking schema ----------
# Registering the schema doesn't itself cause failures - we also need actual
# records on the topic encoded under v2 so the fraud-decisioning engine
# (pinned to v1) wedges. The datagen connector keeps producing healthy v1
# records past the poison offset, so lag grows linearly until reset.
echo "[induce_lag] step 5/6: injecting poison records under the breaking schema..."
if docker ps --format '{{.Names}}' | grep -q '^fraud-decisioning-engine$'; then
  docker exec fraud-decisioning-engine python /app/inject_poison.py \
    | sed 's/^/[induce_lag]   poison> /'
else
  echo "[induce_lag]   (skipped - fraud-decisioning-engine container not running)"
fi
echo

# ---------- 6. confirmation ----------
echo "[induce_lag] step 6/6: current versions for ${SUBJECT}:"
curl --silent --show-error "${SR_PROD}/subjects/${SUBJECT}/versions" \
  | sed 's/^/[induce_lag]   sr> /'
echo

cat <<'DONE'
+======================================================================+
|  *BOOM*  Lag injected.                                               |
|  fraud-decisioning engine should start failing to deserialize new    |
|  records within ~30 seconds, and ledger production will stop.        |
|                                                                      |
|  watch:    lag on cards-prod-euw1's `fraud-decisioning-engine` group |
|            + cards.ledger.posted.v1 message rate dropping to 0       |
|  reset:    bash harness/scenarios/consumer-lag/reset.sh                                     |
+======================================================================+
DONE
