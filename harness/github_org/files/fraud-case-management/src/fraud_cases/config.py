"""Runtime settings, read once from the environment.

Kept free of Kafka imports so the consumer configuration can be unit-tested.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

SCORE_TOPIC = "fraud.score.computed.v1"
CASE_OPENED_TOPIC = "fraud.case.opened.v1"
CASE_RESOLVED_TOPIC = "fraud.case.resolved.v1"
CONSUMER_GROUP = "fraud-case-management"


@dataclass(frozen=True)
class Settings:
    bootstrap_servers: str
    schema_registry_url: str
    database_url: str
    security_protocol: str = "SASL_SSL"
    kafka_username: str = ""
    kafka_password: str = ""
    review_threshold: float = 0.5
    txn_history_url: str = "http://txn-history-builder.cards-servicing.svc:8080"
    card_lifecycle_url: str = "http://card-lifecycle-svc.cards-servicing.svc:8080"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        def required(name: str) -> str:
            value = env.get(name, "").strip()
            if not value:
                raise RuntimeError(f"{name} is not set")
            return value

        return cls(
            bootstrap_servers=required("KAFKA_BOOTSTRAP_SERVERS"),
            schema_registry_url=required("SCHEMA_REGISTRY_URL"),
            database_url=required("FRAUD_CASES_DB_URL"),
            security_protocol=env.get("KAFKA_SECURITY_PROTOCOL", "SASL_SSL"),
            kafka_username=env.get("KAFKA_USERNAME", ""),
            kafka_password=env.get("KAFKA_PASSWORD", ""),
            review_threshold=float(env.get("FRAUD_CASES_REVIEW_THRESHOLD", "0.5")),
            txn_history_url=env.get("TXN_HISTORY_URL", cls.txn_history_url),
            card_lifecycle_url=env.get("CARD_LIFECYCLE_URL", cls.card_lifecycle_url),
        )

    def _security(self) -> dict[str, str]:
        conf = {"security.protocol": self.security_protocol}
        if self.security_protocol.startswith("SASL"):
            conf.update({
                "sasl.mechanisms": "SCRAM-SHA-512",
                "sasl.username": self.kafka_username,
                "sasl.password": self.kafka_password,
            })
        return conf

    def consumer_config(self) -> dict[str, object]:
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": CONSUMER_GROUP,
            "client.id": CONSUMER_GROUP,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            "partition.assignment.strategy": "cooperative-sticky",
            "max.poll.interval.ms": 300000,
            "session.timeout.ms": 45000,
            **self._security(),
        }

    def producer_config(self) -> dict[str, object]:
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": CONSUMER_GROUP,
            "acks": "all",
            "enable.idempotence": True,
            "linger.ms": 5,
            **self._security(),
        }
