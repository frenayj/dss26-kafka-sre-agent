"""Consume authorisation requests, score them and post the score to the ledger.

Records are Avro (ADR-0007), read with the reader schema pinned in schemas/.
We never commit past a record we cannot read: see README, "Fail closed".
"""

import logging
import time
import uuid

from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

from fraud_scoring import metrics
from fraud_scoring.config import Settings
from fraud_scoring.scoring import assess

log = logging.getLogger(__name__)


def to_posting(auth, assessment):
    return {
        "posting_id": str(uuid.uuid4()),
        "auth_id": auth["auth_id"],
        "merchant_id": auth["merchant_id"],
        "amount": float(auth["amount"]),
        "currency": auth.get("currency") or "USD",
        "risk_score": assessment.score,
        "ts": int(time.time() * 1000),
    }


def run(settings: Settings) -> None:
    with open(settings.reader_schema_path) as f:
        reader_schema = f.read()
    with open(settings.ledger_schema_path) as f:
        ledger_schema = f.read()

    registry = SchemaRegistryClient({"url": settings.schema_registry_url})
    deserialise = AvroDeserializer(registry, schema_str=reader_schema)
    serialise = AvroSerializer(registry, ledger_schema)

    consumer = Consumer({
        "bootstrap.servers": settings.bootstrap_servers,
        "group.id": settings.group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    producer = Producer({
        "bootstrap.servers": settings.bootstrap_servers,
        "client.id": "fraud-scoring",
        "acks": "all",
    })
    consumer.subscribe([settings.input_topic])
    log.info("consuming %s as %s", settings.input_topic, settings.group_id)

    # (topic, partition, offset) of a record we could not read. We seek back
    # to it until it can be read; nothing after it is committed.
    held = None

    try:
        while True:
            if held is not None:
                consumer.seek(TopicPartition(*held))
                time.sleep(1)

            msg = consumer.poll(1.0)
            if msg is None:
                producer.poll(0)
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("kafka error: %s", msg.error())
                continue

            where = (msg.topic(), msg.partition(), msg.offset())
            ctx = SerializationContext(msg.topic(), MessageField.VALUE)
            try:
                auth = deserialise(msg.value(), ctx)
            except Exception as exc:
                metrics.DESERIALISATION_ERRORS.labels(str(msg.partition())).inc()
                if held != where:
                    log.error(
                        "cannot read %s[%d]@%d: %s: %s - holding here, not committing past it",
                        *where, type(exc).__name__, exc,
                    )
                held = where
                continue
            if held == where:
                log.info("%s[%d]@%d readable again", *where)
                held = None

            assessment = assess(auth)
            producer.produce(
                settings.ledger_topic,
                key=auth["auth_id"].encode(),
                value=serialise(
                    to_posting(auth, assessment),
                    SerializationContext(settings.ledger_topic, MessageField.VALUE),
                ),
            )
            producer.poll(0)
            consumer.commit(message=msg, asynchronous=False)
            metrics.DECISIONS.labels(assessment.outcome).inc()
            metrics.POSTINGS.inc()
    finally:
        producer.flush(10)
        consumer.close()
