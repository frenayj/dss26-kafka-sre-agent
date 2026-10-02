"""Consume authorisation requests, score them and post the score to the ledger."""

import json
import logging
import time
import uuid

from confluent_kafka import Consumer, KafkaError, Producer

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

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                producer.poll(0)
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("kafka error: %s", msg.error())
                continue

            try:
                auth = json.loads(msg.value())
            except ValueError:
                log.warning(
                    "skipping unreadable record at %s[%d]@%d",
                    msg.topic(), msg.partition(), msg.offset(),
                )
                consumer.commit(message=msg, asynchronous=False)
                continue

            assessment = assess(auth)
            producer.produce(
                settings.ledger_topic,
                key=auth["auth_id"].encode(),
                value=json.dumps(to_posting(auth, assessment)).encode(),
            )
            producer.poll(0)
            consumer.commit(message=msg, asynchronous=False)
    finally:
        producer.flush(10)
        consumer.close()
