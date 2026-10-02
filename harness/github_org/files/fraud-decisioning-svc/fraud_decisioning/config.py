"""Runtime settings for fraud-decisioning-svc.

Everything comes from the environment except the Kafka consumer properties.
The Helm chart renders those from ``kafka.consumer`` in
``deploy/helm/values-<env>.yaml`` into a properties file and points
``KAFKA_CONSUMER_PROPERTIES`` at it, so the consumer can be tuned with a values
change and a rollout instead of a release.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_GROUP_ID = "fraud-decisioning-engine"
DEFAULT_INPUT_TOPIC = "cards.authorisation.requested.v1"
DEFAULT_LEDGER_TOPIC = "cards.ledger.posted.v1"
CLIENT_ID = "fraud-decisioning-svc"

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
DEFAULT_READER_SCHEMA = SCHEMA_DIR / "cards_authorisation_requested_v1.avsc"
DEFAULT_LEDGER_SCHEMA = SCHEMA_DIR / "cards_ledger_posted_v1.avsc"

# INC-2025-03-18-002: batches of 2000 plus a full GC could take longer than
# max.poll.interval.ms. 500 keeps a batch well under a second at peak.
DEFAULT_BATCH_SIZE = 500


class ConfigError(ValueError):
    """The environment or the mounted consumer properties are not usable."""


def read_properties(path: Path) -> dict[str, str]:
    """Parse a ``key=value`` properties file. ``#`` and ``!`` start a comment."""
    props: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            raise ConfigError(f"{path}:{lineno}: expected key=value, got {raw!r}")
        props[key.strip()] = value.strip()
    return props


@dataclass(frozen=True)
class Settings:
    bootstrap_servers: str
    schema_registry_url: str
    input_topic: str = DEFAULT_INPUT_TOPIC
    ledger_topic: str = DEFAULT_LEDGER_TOPIC
    reader_schema_path: Path = DEFAULT_READER_SCHEMA
    ledger_schema_path: Path = DEFAULT_LEDGER_SCHEMA
    consumer_properties: Mapping[str, str] = field(default_factory=dict)
    batch_size: int = DEFAULT_BATCH_SIZE
    poll_timeout_s: float = 1.0
    blocked_retry_s: float = 5.0
    ledger_flush_timeout_s: float = 30.0
    metrics_port: int = 9102

    def consumer_config(self) -> dict[str, str]:
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": CLIENT_ID,
            "group.id": DEFAULT_GROUP_ID,
            "auto.offset.reset": "earliest",
        }
        config.update(self.consumer_properties)
        # Offsets are committed by the decisioning loop once the ledger
        # posting is acknowledged. Letting librdkafka commit on a timer would
        # move the group past records that were never posted.
        if str(config.get("enable.auto.commit", "false")).lower() != "false":
            raise ConfigError(
                "enable.auto.commit must be false: offsets are committed only "
                "after the ledger posting is acknowledged"
            )
        config["enable.auto.commit"] = "false"
        return config

    def producer_config(self) -> dict[str, str]:
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": CLIENT_ID,
            "acks": "all",
            "enable.idempotence": "true",
            "compression.type": "lz4",
            "linger.ms": "5",
        }

    @property
    def group_id(self) -> str:
        return self.consumer_config()["group.id"]


def _number(environ: Mapping[str, str], name: str, default, kind):
    raw = environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return kind(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not a valid {kind.__name__}") from None


def from_env(environ: Mapping[str, str] = os.environ) -> Settings:
    missing = [n for n in ("KAFKA_BOOTSTRAP_SERVERS", "SCHEMA_REGISTRY_URL") if not environ.get(n)]
    if missing:
        raise ConfigError(f"required environment variable(s) not set: {', '.join(missing)}")

    props_path = environ.get("KAFKA_CONSUMER_PROPERTIES")
    props = read_properties(Path(props_path)) if props_path else {}

    return Settings(
        bootstrap_servers=environ["KAFKA_BOOTSTRAP_SERVERS"],
        schema_registry_url=environ["SCHEMA_REGISTRY_URL"],
        input_topic=environ.get("INPUT_TOPIC", DEFAULT_INPUT_TOPIC),
        ledger_topic=environ.get("LEDGER_TOPIC", DEFAULT_LEDGER_TOPIC),
        reader_schema_path=Path(environ.get("READER_SCHEMA_PATH", DEFAULT_READER_SCHEMA)),
        ledger_schema_path=Path(environ.get("LEDGER_SCHEMA_PATH", DEFAULT_LEDGER_SCHEMA)),
        consumer_properties=props,
        batch_size=_number(environ, "BATCH_SIZE", DEFAULT_BATCH_SIZE, int),
        blocked_retry_s=_number(environ, "BLOCKED_RETRY_SECONDS", 5.0, float),
        metrics_port=_number(environ, "METRICS_PORT", 9102, int),
    )
