"""Consume fraud.score.computed.v1 and open cases.

Offsets are committed only after the case row is written and the
fraud.case.opened.v1 event is acknowledged, so a crash replays the score
instead of losing the case. The ON CONFLICT on triggering_auth_id makes the
replay harmless.
"""

from __future__ import annotations

import logging
import signal

from confluent_kafka import Consumer, KafkaError, Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer

from fraud_cases.config import CASE_OPENED_TOPIC, SCORE_TOPIC, Settings
from fraud_cases.lookup import CardOwnerLookup
from fraud_cases.store import CaseStore
from fraud_cases.triage import triage

log = logging.getLogger("fraud_cases.consumer")


def _schema(path: str) -> str:
    with open(path) as fh:
        return fh.read()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    registry = SchemaRegistryClient({"url": settings.schema_registry_url})
    deserialize = AvroDeserializer(registry, _schema("schemas/fraud.score.computed.v1.avsc"))
    serialize = AvroSerializer(registry, _schema("schemas/fraud.case.opened.v1.avsc"),
                               conf={"auto.register.schemas": False, "use.latest.version": True})
    key = StringSerializer("utf_8")

    consumer = Consumer(settings.consumer_config())
    producer = Producer(settings.producer_config())
    store = CaseStore(settings.database_url)
    owners = CardOwnerLookup(settings.txn_history_url, settings.card_lifecycle_url)

    running = True

    def stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    consumer.subscribe([SCORE_TOPIC])
    log.info("consuming %s as %s", SCORE_TOPIC, settings.consumer_config()["group.id"])

    try:
        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("kafka error: %s", msg.error())
                continue

            score = deserialize(msg.value(), SerializationContext(msg.topic(), MessageField.VALUE))
            decision = triage(score["score"], score["decision"], score.get("rule_matches") or [],
                              settings.review_threshold)
            if decision.open_case:
                owner = owners.for_auth(score["auth_id"])
                case = store.open_case(customer_id=owner.customer_id, card_token=owner.card_token,
                                       trigger=decision.trigger, priority=decision.priority,
                                       triggering_auth_id=score["auth_id"])
                if case is not None:
                    producer.produce(
                        CASE_OPENED_TOPIC,
                        key=key(case["case_id"]),
                        value=serialize({
                            "case_id": case["case_id"],
                            "customer_id": case["customer_id"],
                            "card_token": case["card_token"],
                            "trigger": case["trigger"],
                            "triggering_auth_id": case["triggering_auth_id"],
                            "priority": case["priority"],
                            "opened_at": case["opened_at"],
                        }, SerializationContext(CASE_OPENED_TOPIC, MessageField.VALUE)),
                    )
                    producer.flush(10)
            consumer.commit(message=msg, asynchronous=False)
    finally:
        consumer.close()
        owners.close()


if __name__ == "__main__":
    main()
