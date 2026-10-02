"""Deploy the baseline-traffic generator: kafka-connect-datagen.

It runs as a Kafka Connect *source* connector inside the fast-data-dev worker,
producing healthy ``cards.authorisation.requested.v1`` Avro records - the
steady-state traffic the fraud-decisioning engine consumes. Incidents are
induced separately (see harness scenarios), so this only has to keep clean
baseline traffic flowing.

To keep the topic's registered schema byte-identical to
``harness/stack/schemas/cards_authorisation_requested_v1.avsc`` (what the fraud engine
and the reset/break scripts expect), we pre-register that canonical schema and
pin the connector's AvroConverter to its id with
``auto.register.schemas=false``. The ``arg.properties`` in the datagen
template only drive record *generation*, never what's registered.

``seed`` (the only subcommand) is idempotent. reset.sh re-runs it after a
subject purge to re-pin the connector to the freshly registered schema id.

Stdlib-only on purpose (urllib, not requests) so it runs under any python3 -
both in the seeder container and on the host.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ENV = "cards-prod-euw1"
KAFKA_CONTAINER = "demo-kafka-prod"
AUTH_TOPIC = "cards.authorisation.requested.v1"
CONNECTOR_NAME = "datagen-cards-auth-prod"
# Canonical schema (what gets registered).
CANONICAL_SCHEMA = REPO_ROOT / "harness" / "stack" / "schemas" / "cards_authorisation_requested_v1.avsc"
# The generation template from harness/stack/datagen/, as baked into the broker image
# by harness/stack/fast-data-dev.Dockerfile. The connector loads it via
# schema.filename (the schema.string path strips arg.properties off primitive
# types).
TEMPLATE_PATH = "/opt/lensesio/datagen/cards_auth_prod.avsc"
# max.interval is the *max* random gap between records (avg = half), so the
# rate is about 2000 / max.interval msg/s: 16 gives ~120/s.
MAX_INTERVAL_MS = 16

# The Connect worker resolves the registry over the compose network.
WORKER_SR_URL = "http://demo-kafka-prod:8081"
# What this script calls: host-mapped ports by default; the seeder container
# sets CONNECT_PROD_URL / SCHEMA_REGISTRY_PROD to the in-network URLs.
CONNECT_URL = (
    os.environ.get("CONNECT_PROD_URL") or f"http://localhost:{os.environ.get('HOST_PORT_CONNECT_PROD') or '8093'}"
).rstrip("/")
SR_URL = (
    os.environ.get("SCHEMA_REGISTRY_PROD") or f"http://localhost:{os.environ.get('HOST_PORT_SR_PROD') or '8081'}"
).rstrip("/")


# ---------------------------------------------------------------------------
# HTTP / broker helpers
# ---------------------------------------------------------------------------

def _request(url: str, *, method: str = "GET", payload: dict | None = None,
             timeout: int = 15) -> tuple[int, str]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:300]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, str(exc)


def wait_for_connect(*, attempts: int = 30) -> bool:
    for _ in range(attempts):
        status, _ = _request(f"{CONNECT_URL}/connectors", timeout=3)
        if status == 200:
            return True
        time.sleep(2)
    return False


def ensure_topic() -> None:
    """Create the auth topic with a single partition (idempotent).

    The single-partition topology is part of the demo (the agent diagnoses
    "1 partition → no consumer-scale headroom"), so we pin it rather than
    relying on broker auto-create defaults.
    """
    cmd = [
        "docker", "exec", KAFKA_CONTAINER,
        "kafka-topics", "--bootstrap-server", "localhost:9092",
        "--create", "--if-not-exists",
        "--topic", AUTH_TOPIC, "--partitions", "1", "--replication-factor", "1",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            print(f"[datagen]   WARN topic-create: {(r.stderr or r.stdout).strip()[:200]}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"[datagen]   WARN topic-create: {exc}")


def register_canonical_schema() -> int | None:
    """Register the canonical v1 schema as ``<topic>-value`` (idempotent).

    Returns the schema id so the connector can pin to it.
    """
    payload = {"schema": CANONICAL_SCHEMA.read_text()}
    status, body = _request(
        f"{SR_URL}/subjects/{AUTH_TOPIC}-value/versions",
        method="POST", payload=payload,
    )
    if status != 200:
        print(f"[datagen]   WARN schema-register: HTTP {status} {body[:150]}")
        return None
    try:
        return int(json.loads(body)["id"])
    except (ValueError, KeyError):
        print(f"[datagen]   WARN could not parse schema id: {body[:150]}")
        return None


def datagen_config(schema_id: int) -> dict[str, str]:
    return {
        "connector.class": "io.confluent.kafka.connect.datagen.DatagenConnector",
        "tasks.max": "1",
        "kafka.topic": AUTH_TOPIC,
        # Load the baked template from the broker image via schema.filename -
        # NOT schema.string, which drops arg.properties off primitive types.
        "schema.filename": TEMPLATE_PATH,
        "schema.keyfield": "auth_id",
        "max.interval": str(MAX_INTERVAL_MS),
        "iterations": "-1",
        "key.converter": "org.apache.kafka.connect.storage.StringConverter",
        "value.converter": "io.confluent.connect.avro.AvroConverter",
        "value.converter.schema.registry.url": WORKER_SR_URL,
        "value.converter.auto.register.schemas": "false",
        # Pin to the canonical v1 schema *id* (not use.latest.version): the
        # consumer-lag scenario registers an incompatible v2 as the latest
        # version, and we need datagen to keep emitting healthy v1 records so
        # consumer lag grows. use.latest.version would switch to v2 and the
        # task would die.
        "value.converter.use.schema.id": str(schema_id),
    }


def put_connector(config: dict[str, str]) -> tuple[bool, str]:
    status, body = _request(
        f"{CONNECT_URL}/connectors/{CONNECTOR_NAME}/config", method="PUT", payload=config,
    )
    if status in (200, 201):
        return True, f"HTTP {status}"
    return False, f"HTTP {status} {body}"


def connector_status() -> str:
    status, body = _request(f"{CONNECT_URL}/connectors/{CONNECTOR_NAME}/status", timeout=5)
    if status != 200:
        return f"(status unavailable: HTTP {status})"
    try:
        d = json.loads(body)
        conn = d["connector"]["state"]
        tasks = ", ".join(f"task-{t['id']}={t['state']}" for t in d.get("tasks", []))
        return f"connector={conn} {tasks or '(no tasks yet)'}"
    except (ValueError, KeyError):
        return body[:200]


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_seed() -> int:
    """Ensure topic + canonical schema, then create/upsert the datagen connector
    pinned to that schema's id."""
    print(f"[datagen] {ENV}: waiting for Connect at {CONNECT_URL}...")
    if not wait_for_connect():
        print(f"[datagen] [FAIL] {ENV}: Connect not reachable - is the stack up?", file=sys.stderr)
        return 1
    ensure_topic()
    schema_id = register_canonical_schema()
    if schema_id is None:
        print(f"[datagen] [FAIL] {ENV}: no schema id - cannot pin the converter", file=sys.stderr)
        return 1
    ok, msg = put_connector(datagen_config(schema_id))
    print(f"[datagen] [{'ok ' if ok else 'FAIL'}] {ENV}: {CONNECTOR_NAME} (schema id {schema_id}) - {msg}")
    time.sleep(3)
    print(f"[datagen] {ENV}: {connector_status()}")
    return 0 if ok else 1


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if cmd != "seed":
        print(f"usage: {sys.argv[0]} [seed]", file=sys.stderr)
        return 2
    return cmd_seed()


if __name__ == "__main__":
    sys.exit(main())
