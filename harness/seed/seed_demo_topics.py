"""Seed the 30 catalogue-only "fake" topics on the demo Kafka cluster.

For each topic in ``demo_topics.topics_to_seed()``:

1. Create the topic on the broker via ``docker exec ... kafka-topics --create``
   (idempotent: ``--if-not-exists`` makes re-runs cheap).
2. Register the topic's Avro value schema as ``<topic>-value`` in the
   Schema Registry (idempotent: re-registering an identical schema is a
   no-op against the same subject).

No data is produced - these topics exist purely to make the catalogue look
like a real cards-platform.

This script does NOT apply HQ catalogue descriptions or tags - that's
``apply_topic_metadata.py``'s job, which reads from the same
``demo_topics.TOPICS`` list. The seeder runs both, in order.

Prereqs: ``docker`` on PATH with ``demo-kafka-prod`` running, and its Schema
Registry reachable (host port 8081, or ``SCHEMA_REGISTRY_PROD``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any

import requests
from demo_topics import TopicSpec, topics_to_seed

# The broker container (for ``docker exec ... kafka-topics``), fixed by
# harness/stack/docker-compose.yml.
KAFKA_CONTAINER = "demo-kafka-prod"

# Host-mapped by default; the seeder container sets SCHEMA_REGISTRY_PROD to
# the in-network URL.
SR_URL = (
    os.environ.get("SCHEMA_REGISTRY_PROD") or f"http://localhost:{os.environ.get('HOST_PORT_SR_PROD') or '8081'}"
).rstrip("/")

SR_HEADERS = {"Content-Type": "application/vnd.schemaregistry.v1+json"}


def kafka_topics_create(topic: str, partitions: int) -> tuple[bool, str]:
    """Create a topic on the broker. Returns (created_or_already_exists, msg)."""
    cmd = [
        "docker", "exec", KAFKA_CONTAINER,
        "kafka-topics",
        "--bootstrap-server", "localhost:9092",
        "--create", "--if-not-exists",
        "--topic", topic,
        "--partitions", str(partitions),
        "--replication-factor", "1",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError:
        return False, "docker not on PATH"

    # kafka-topics --if-not-exists is silent when the topic already exists, and
    # prints "Created topic <name>." on creation. Either way: rc==0 = success.
    if r.returncode == 0:
        msg = (r.stdout or "").strip() or "ok (already existed)"
        return True, msg
    return False, (r.stderr or r.stdout or "").strip()[:300]


def register_schema(
    session: requests.Session, subject: str, avro_schema: dict[str, Any]
) -> tuple[bool, str]:
    """POST the schema to ``<SR_URL>/subjects/<subject>/versions``.

    Confluent SR is idempotent on identical schemas - the response carries
    the existing schema's id when the content matches.
    """
    url = f"{SR_URL}/subjects/{subject}/versions"
    payload = {"schema": json.dumps(avro_schema)}
    try:
        r = session.post(url, headers=SR_HEADERS, json=payload, timeout=10)
    except requests.RequestException as exc:
        return False, str(exc)

    if r.ok:
        try:
            body = r.json()
            sid = body.get("id")
            return True, f"schema_id={sid}"
        except ValueError:
            return True, "ok"
    return False, f"HTTP {r.status_code} {r.text[:200]}"


def wait_for_sr(session: requests.Session, *, attempts: int = 30) -> bool:
    """Block until the Schema Registry answers ``/subjects`` or attempts run out."""
    for _ in range(attempts):
        try:
            r = session.get(f"{SR_URL}/subjects", timeout=3)
            if r.ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def seed_one(session: requests.Session, spec: TopicSpec) -> tuple[bool, str]:
    """Seed a single topic. Returns (ok, summary line)."""
    ok_topic, msg_topic = kafka_topics_create(spec.name, spec.partitions)
    if not ok_topic:
        return False, f"topic-create failed: {msg_topic}"

    assert spec.avro_schema is not None  # topics_to_seed() filters these out
    subject = f"{spec.name}-value"
    ok_schema, msg_schema = register_schema(session, subject, spec.avro_schema)
    if not ok_schema and msg_schema.startswith("HTTP 409"):
        # The catalogue schema changed incompatibly since it was seeded (e.g.
        # an Avro namespace rename). These topics carry no data, so nothing
        # depends on the old version: purge the subject and register afresh.
        for suffix in ("", "?permanent=true"):
            session.delete(f"{SR_URL}/subjects/{subject}{suffix}", timeout=10)
        ok_schema, msg_schema = register_schema(session, subject, spec.avro_schema)
        msg_schema = f"replaced incompatible subject; {msg_schema}"
    if not ok_schema:
        return False, f"schema-register failed: {msg_schema}"

    return True, f"{msg_topic}; {msg_schema}"


def main() -> int:
    seedable = topics_to_seed()
    s = requests.Session()

    print(f"[seed] waiting for Schema Registry at {SR_URL}...")
    if not wait_for_sr(s):
        print(
            f"[seed] ERROR: Schema Registry at {SR_URL} is not reachable. "
            f"Is the docker stack up? (container: {KAFKA_CONTAINER})",
            file=sys.stderr,
        )
        return 1
    print(f"[seed] {len(seedable)} topics to seed")

    applied = 0
    failed = 0
    for spec in seedable:
        try:
            ok, msg = seed_one(s, spec)
        except Exception as exc:  # noqa: BLE001 - never want to abort the loop on a single bad topic
            ok, msg = False, f"unhandled: {exc!r}"

        print(f"[seed] [{'ok ' if ok else 'FAIL'}] {spec.name}: {msg}")
        if ok:
            applied += 1
        else:
            failed += 1

    print(f"[seed] done - {applied} applied, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
