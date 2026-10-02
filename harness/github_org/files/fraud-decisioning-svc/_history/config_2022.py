"""Settings from the environment."""

import os
from dataclasses import dataclass
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


@dataclass(frozen=True)
class Settings:
    bootstrap_servers: str
    schema_registry_url: str
    group_id: str = "fraud-scoring-consumer"
    input_topic: str = "cards.authorisation.requested.v1"
    ledger_topic: str = "cards.ledger.posted.v1"
    reader_schema_path: Path = SCHEMA_DIR / "cards_authorisation_requested_v1.avsc"
    ledger_schema_path: Path = SCHEMA_DIR / "cards_ledger_posted_v1.avsc"
    metrics_port: int = 9102


def from_env() -> Settings:
    return Settings(
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        schema_registry_url=os.environ["SCHEMA_REGISTRY_URL"],
        group_id=os.environ.get("CONSUMER_GROUP", "fraud-scoring-consumer"),
        input_topic=os.environ.get("INPUT_TOPIC", "cards.authorisation.requested.v1"),
        ledger_topic=os.environ.get("LEDGER_TOPIC", "cards.ledger.posted.v1"),
        metrics_port=int(os.environ.get("METRICS_PORT", "9102")),
    )
