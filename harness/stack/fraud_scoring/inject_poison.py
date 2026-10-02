"""One-shot poison producer for the SRE demo.

Produces a handful of records to ``cards.authorisation.requested.v1``
encoded under the **breaking v2 schema** (``amount: string``, no
``country``). The v1-reader fraud-decisioning engine can't project these
onto its reader schema and wedges on the first poison record. The datagen
connector keeps producing healthy v1 records past it → lag grows + ledger
production stops = demo evidence.

Called from ``harness/scenarios/consumer-lag/induce.sh`` after the breaking schema has been
registered in the Schema Registry. Idempotent: running twice just adds
another batch of poison records.

Environment:
    BOOTSTRAP                 - Kafka bootstrap (default: demo-kafka-prod:9092)
    SCHEMA_REGISTRY_URL       - SR (default: http://demo-kafka-prod:8081)
    BREAKING_SCHEMA_PATH      - path to v2 .avsc (default: /etc/schemas/cards_authorisation_requested_v1_breaking.avsc)
    TOPIC                     - topic (default: cards.authorisation.requested.v1)
    POISON_COUNT              - how many records to inject (default: 5)
"""

from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
import uuid

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer

BOOTSTRAP = os.environ.get("BOOTSTRAP", "demo-kafka-prod:9092")
SR_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://demo-kafka-prod:8081")
SCHEMA_PATH = os.environ.get(
    "BREAKING_SCHEMA_PATH", "/etc/schemas/cards_authorisation_requested_v1_breaking.avsc"
)
TOPIC = os.environ.get("TOPIC", "cards.authorisation.requested.v1")
COUNT = int(os.environ.get("POISON_COUNT", "5"))

# Same merchants the baseline traffic uses (harness/stack/datagen/*.avsc).
MERCHANTS = ("mch_lumen_coffee", "mch_halcyon_retail", "mch_brightline_saas")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [poison-producer] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("poison")


def main() -> None:
    # The repo copy carries a doc-only "_comment_break" key; drop it so the
    # writer schema is exactly the v2 the producer's pipeline registered.
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    schema.pop("_comment_break", None)
    schema_str = json.dumps(schema)

    sr_client = SchemaRegistryClient({"url": SR_URL})
    serializer = AvroSerializer(sr_client, schema_str)
    key_serializer = StringSerializer("utf_8")

    producer = Producer({"bootstrap.servers": BOOTSTRAP})
    log.info("injecting %d poison record(s) into %s under breaking v2 schema", COUNT, TOPIC)

    for _ in range(COUNT):
        # Ordinary-looking gateway traffic written under v2: amount is a
        # decimal string (no Avro promotion to the v1 reader's `double`) and
        # there is no country field. Nothing in the payload names the change
        # that caused it - the agent can sample these records via Lenses, and
        # the evidence has to be the shape, not a label.
        value = {
            "auth_id": str(uuid.uuid4()),
            "card_token": f"tok_{random.randint(100000, 999999)}",
            "merchant_id": random.choice(MERCHANTS),
            "amount": f"{random.uniform(4, 240):.2f}",
            "currency": random.choice(("EUR", "GBP", "USD")),
            "ts": int(time.time() * 1000),
            "risk_signals": random.choice(([], [], ["VELOCITY_OK"], ["NEW_DEVICE"])),
            "channel": random.choice(("ECOM", "CARD_PRESENT", "RECURRING")),
            "tier": "cards-prod-euw1",
        }
        producer.produce(
            topic=TOPIC,
            key=key_serializer(str(uuid.uuid4())),
            value=serializer(value, SerializationContext(TOPIC, MessageField.VALUE)),
        )
        producer.poll(0)

    producer.flush(10)
    log.info("done - %d poison record(s) flushed", COUNT)


if __name__ == "__main__":
    main()
