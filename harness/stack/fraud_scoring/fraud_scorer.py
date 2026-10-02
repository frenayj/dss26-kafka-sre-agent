"""Fraud-decisioning engine - the lag victim for the SRE demo.

Subscribes to ``cards.authorisation.requested.v1`` on the prod cards cluster
as consumer group ``fraud-decisioning-engine`` with the **v1 reader schema
pinned**. For each healthy auth it produces a ``LedgerPosting`` record to
``cards.ledger.posted.v1`` - that's the downstream signal the SRE agent
observes ("ledger ingestion stalled").

When ``induce_lag.sh`` registers a v2 schema that changes ``amount`` from
``double -> string`` and drops ``country``, this consumer's Avro
deserializer rejects the new records (reader-schema projection fails). We
never commit on failure, so the consumer wedges on the first poison message
and lag grows linearly with the producer's output - **and ledger production
stops**, which is exactly the "stalled poison-message + downstream silence"
pattern the ``kafka-consumer-lag`` skill expects to find.

Healthy operation:
    "scored ..." once per record, advancing offsets, ledger topic receiving
    one record per scored auth.

Broken operation:
    "DESERIALIZE FAILED" once per second, offset frozen, lag grows ~30-60
    rec/sec, ledger topic stops getting new records.

Environment:
    BOOTSTRAP             - Kafka bootstrap (default: demo-kafka-prod:9092)
    SCHEMA_REGISTRY_URL   - SR (default: http://demo-kafka-prod:8081)
    READER_SCHEMA_PATH    - path to v1 reader .avsc for the auth topic
                            (default: /etc/schemas/cards_authorisation_requested_v1.avsc)
    LEDGER_SCHEMA_PATH    - path to ledger writer .avsc
                            (default: /etc/schemas/cards_ledger_posted_v1.avsc)
    CONSUMER_GROUP        - group id (default: fraud-decisioning-engine)
    TOPIC                 - input topic (default: cards.authorisation.requested.v1)
    LEDGER_TOPIC          - output topic (default: cards.ledger.posted.v1)
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
import uuid

from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer

BOOTSTRAP = os.environ.get("BOOTSTRAP", "demo-kafka-prod:9092")
SR_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://demo-kafka-prod:8081")
SCHEMA_PATH = os.environ.get(
    "READER_SCHEMA_PATH", "/etc/schemas/cards_authorisation_requested_v1.avsc"
)
LEDGER_SCHEMA_PATH = os.environ.get(
    "LEDGER_SCHEMA_PATH", "/etc/schemas/cards_ledger_posted_v1.avsc"
)
GROUP_ID = os.environ.get("CONSUMER_GROUP", "fraud-decisioning-engine")
TOPIC = os.environ.get("TOPIC", "cards.authorisation.requested.v1")
LEDGER_TOPIC = os.environ.get("LEDGER_TOPIC", "cards.ledger.posted.v1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [fraud-decisioning] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("fraud-decisioning")


def _score(value: dict) -> tuple[float, str]:
    """Toy scorer - risk_signals nudge the score up; otherwise random low score."""
    signals = value.get("risk_signals") or []
    base = random.uniform(0.05, 0.25)
    bump = 0.2 * len(signals)
    score = min(1.0, base + bump)
    if score >= 0.8:
        decision = "DECLINE"
    elif score >= 0.5:
        decision = "REVIEW"
    else:
        decision = "APPROVE"
    return score, decision


def main() -> None:
    log.info(
        "starting | bootstrap=%s sr=%s group=%s in=%s out=%s",
        BOOTSTRAP, SR_URL, GROUP_ID, TOPIC, LEDGER_TOPIC,
    )
    log.info("reader schema pinned to %s (v1) - strict projection enabled", SCHEMA_PATH)

    with open(SCHEMA_PATH) as f:
        reader_schema = f.read()
    with open(LEDGER_SCHEMA_PATH) as f:
        ledger_schema = f.read()

    sr_client = SchemaRegistryClient({"url": SR_URL})
    deserializer = AvroDeserializer(sr_client, schema_str=reader_schema)
    ledger_serializer = AvroSerializer(sr_client, ledger_schema)
    key_serializer = StringSerializer("utf_8")

    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([TOPIC])

    producer = Producer({
        "bootstrap.servers": BOOTSTRAP,
        "client.id": "fraud-decisioning-engine",
        "acks": "all",
        "compression.type": "lz4",
    })

    scored = 0
    failed = 0
    posted = 0
    last_report = time.time()
    # Once we hit a poison record we wedge on it - librdkafka advances the
    # internal position on every poll, so to actually stall we must seek the
    # partition back to the failed offset before each retry. This mirrors
    # the real "stalled poison-message" SRE scenario the demo dramatizes:
    # one bad record holds the entire partition hostage.
    wedge: tuple[str, int, int] | None = None  # (topic, partition, offset)

    try:
        while True:
            if wedge is not None:
                t, p, o = wedge
                consumer.seek(TopicPartition(t, p, o))
                time.sleep(1)

            msg = consumer.poll(1.0)
            if msg is None:
                # Flush ledger producer between polls to keep latency bounded.
                producer.poll(0)
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                log.error("kafka error: %s", msg.error())
                continue

            ctx = SerializationContext(msg.topic(), MessageField.VALUE)
            try:
                value = deserializer(msg.value(), ctx)
            except Exception as exc:
                failed += 1
                if wedge is None:
                    wedge = (msg.topic(), msg.partition(), msg.offset())
                    log.error(
                        "WEDGED at offset %d: %s - will retry this offset forever (lag grows, ledger stops)",
                        msg.offset(), type(exc).__name__,
                    )
                elif failed % 30 == 0:
                    log.error(
                        "still wedged at offset %d (retries=%d, %s)",
                        wedge[2], failed, type(exc).__name__,
                    )
                continue

            risk_score, decision = _score(value)
            posting = {
                "posting_id": str(uuid.uuid4()),
                "auth_id": value["auth_id"],
                "merchant_id": value["merchant_id"],
                "amount": float(value["amount"]),
                "currency": value.get("currency") or "USD",
                "risk_score": risk_score,
                "decision": decision,
                "ts": int(time.time() * 1000),
            }
            producer.produce(
                topic=LEDGER_TOPIC,
                key=key_serializer(posting["auth_id"]),
                value=ledger_serializer(
                    posting, SerializationContext(LEDGER_TOPIC, MessageField.VALUE)
                ),
            )
            producer.poll(0)
            consumer.commit(message=msg, asynchronous=False)
            scored += 1
            posted += 1

            now = time.time()
            if now - last_report >= 10:
                log.info(
                    "scored=%d posted=%d failed=%d (last 10s tick)",
                    scored, posted, failed,
                )
                last_report = now
    finally:
        producer.flush(10)
        consumer.close()


if __name__ == "__main__":
    main()
