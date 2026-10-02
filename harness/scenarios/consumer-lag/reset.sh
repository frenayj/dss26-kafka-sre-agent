#!/usr/bin/env bash
# reset.sh - restore the cards-prod-euw1 Schema Registry to a clean v1 state,
# restore BACKWARD compatibility, and bounce the fraud-decisioning engine so
# the next scenario starts from green.
#
# Safe to run any time, including before the very first scenario.

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
CONNECT_PROD="${CONNECT_PROD_URL:-http://localhost:${HOST_PORT_CONNECT_PROD:-8093}}"
AUTH_TOPIC="cards.authorisation.requested.v1"
LEDGER_TOPIC="cards.ledger.posted.v1"
SUBJECT="${AUTH_TOPIC}-value"
LEDGER_SUBJECT="${LEDGER_TOPIC}-value"
ORIG_SCHEMA="${REPO_ROOT}/harness/stack/schemas/cards_authorisation_requested_v1.avsc"
SR_HEADER='Content-Type: application/vnd.schemaregistry.v1+json'
# The kafka-connect-datagen source connector that produces baseline traffic.
DATAGEN_CONNECTOR="datagen-cards-auth-prod"

# Prefer the repo venv; the seed and GitHub helpers are stdlib-only.
PY="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PY}" ]] || PY="python3"

# ---------- banner ----------
cat <<'BANNER'
+=================================================================+
|  RESET  -  return cards-prod-euw1 to a clean scenario state     |
+=================================================================+
BANNER

echo "[reset] target schema registry: ${SR_PROD}"
echo

# ---------- 0. GitHub: revert the producer change ----------
# With GitHub live, the schema change is a merged merchant-gateway PR; roll it
# back with a revert PR so main matches the v1 schema the steps below restore.
# shellcheck source=github_org/lib.sh
source "${REPO_ROOT}/harness/github_org/lib.sh"
if gh_scenario_enabled; then
  echo "[reset] step 0/5: reverting the merchant-gateway change on GitHub (dss26-org)..."
  gh_run reset scenario.py revert consumer-lag \
    || echo "[reset] WARN: GitHub revert failed - main may still carry the v2 schema" >&2
  echo
fi

# ---------- 1. reachability ----------
echo "[reset] step 1/5: verifying prod Schema Registry is reachable..."
if ! curl --silent --show-error --fail --max-time 5 "${SR_PROD}/subjects" >/dev/null; then
  echo "[reset] WARN: prod Schema Registry not reachable at ${SR_PROD}" >&2
  echo "[reset]       (skipping schema cleanup - bring the docker stack up first)" >&2
else
  echo "[reset] ok - SR is reachable"
fi
echo

# ---------- 2. clean slate: drop the topics + purge the SR subjects --------
# We must wipe the topic too, not just the SR. The fraud-decisioning engine
# is pinned to a v1 reader schema and reads records by looking up the WRITER
# schema by ID. After we hard-delete the SR subject, those writer IDs are
# orphaned - every existing record on the topic becomes unreadable. So pair
# the schema purge with a topic delete: step 5 reseeds the datagen connector,
# which recreates the input topic and pins it to the re-registered v1 schema.
# We also wipe the ledger topic + subject so the consumer's ledger output
# starts clean for the next scenario.
echo "[reset] step 2/5: dropping topics + purging SR subjects..."
# Stop the baseline producer + consumer first so the recreate races cleanly.
# Deleting the datagen connector stops it; step 5 creates it again.
if command -v docker >/dev/null 2>&1; then
  curl --silent -X DELETE "${CONNECT_PROD}/connectors/${DATAGEN_CONNECTOR}" >/dev/null 2>&1 || true
  echo "[reset]   deleted producer connector (${DATAGEN_CONNECTOR})"
  docker stop fraud-decisioning-engine >/dev/null 2>&1 || true
  # Best-effort topic deletes on the prod broker.
  for t in "${AUTH_TOPIC}" "${LEDGER_TOPIC}"; do
    docker exec demo-kafka-prod kafka-topics \
        --bootstrap-server localhost:9092 \
        --delete --topic "${t}" 2>&1 \
      | sed 's/^/[reset]   kafka> /' || true
  done
fi
if curl --silent --show-error --fail --max-time 5 "${SR_PROD}/subjects" >/dev/null 2>&1; then
  for s in "${SUBJECT}" "${LEDGER_SUBJECT}"; do
    curl --silent --show-error -X DELETE "${SR_PROD}/subjects/${s}" \
      | sed 's/^/[reset]   sr> /' || true
    curl --silent --show-error -X DELETE "${SR_PROD}/subjects/${s}?permanent=true" \
      | sed 's/^/[reset]   sr> /' || true
  done
  echo "[reset] subjects purged"
else
  echo "[reset] (SR unreachable - skipping subject purge)"
fi
echo

# ---------- 3. re-register the original schema ----------
echo "[reset] step 3/5: re-registering the original (clean) schema as v1..."
if [[ ! -f "${ORIG_SCHEMA}" ]]; then
  echo "[reset] ERROR: original schema not found at ${ORIG_SCHEMA}" >&2
  exit 1
fi

if curl --silent --show-error --fail --max-time 5 "${SR_PROD}/subjects" >/dev/null 2>&1; then
  orig_payload=$(python3 -c 'import json, sys; print(json.dumps({"schema": sys.stdin.read()}))' < "${ORIG_SCHEMA}")
  curl --silent --show-error \
    -X POST \
    -H "${SR_HEADER}" \
    --data "${orig_payload}" \
    "${SR_PROD}/subjects/${SUBJECT}/versions" \
    | sed 's/^/[reset]   sr> /'
else
  echo "[reset] (skipped - SR unreachable)"
fi
echo

# ---------- 4. restore BACKWARD compatibility ----------
echo "[reset] step 4/5: restoring subject compatibility to BACKWARD..."
if curl --silent --show-error --fail --max-time 5 "${SR_PROD}/subjects" >/dev/null 2>&1; then
  curl --silent --show-error \
    -X PUT \
    -H "${SR_HEADER}" \
    --data '{"compatibility":"BACKWARD"}' \
    "${SR_PROD}/config/${SUBJECT}" \
    | sed 's/^/[reset]   sr> /'
else
  echo "[reset] (skipped - SR unreachable)"
fi
echo

# ---------- 5. restart producer + consumer ----------
# Step 2 stopped the baseline producer and the consumer, and deleted the topics.
# Reseed the producer so the auth topic is recreated under v1 (the reseed also
# re-pins the connector to the new schema id), then bring the consumer back.
# The consumer group's committed offsets were wiped along with the topic, so
# it starts from earliest (= the new offset 0 of the recreated topic) and
# reads healthy v1 records. The ledger topic gets recreated on the consumer's
# first successful produce.
echo "[reset] step 5/5: restarting producer + consumer..."
if command -v docker >/dev/null 2>&1; then
  "${PY}" "${REPO_ROOT}/harness/seed/seed_datagen.py" seed | sed 's/^/[reset]   /' || true
  # Brief pause so the producer has produced under the re-registered schema
  # before the consumer's first poll. Avoids a transient warning at startup.
  sleep 3
  if docker ps -a --format '{{.Names}}' | grep -qx 'fraud-decisioning-engine'; then
    docker start fraud-decisioning-engine >/dev/null \
      && echo "[reset]   started fraud-decisioning-engine"
  else
    echo "[reset]   no container named 'fraud-decisioning-engine' (skipping consumer)"
  fi
else
  echo "[reset]   docker not on PATH - skip producer/consumer restart"
fi
echo

cat <<'DONE'
+============================================================+
|  Reset complete - cluster ready for the next scenario      |
|  next:   bash harness/scenarios/consumer-lag/induce.sh    (when you're ready) |
+============================================================+
DONE
