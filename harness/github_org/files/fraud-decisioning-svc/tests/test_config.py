from pathlib import Path

import pytest

from fraud_decisioning import config

ENV = {
    "KAFKA_BOOTSTRAP_SERVERS": "broker-1:9092",
    "SCHEMA_REGISTRY_URL": "http://registry:8081",
}


def test_read_properties_skips_comments_and_blank_lines(tmp_path: Path):
    path = tmp_path / "consumer.properties"
    path.write_text(
        "# rendered by the chart\n"
        "group.id=fraud-decisioning-engine\n"
        "\n"
        "! legacy comment style\n"
        "session.timeout.ms = 45000\n"
    )
    assert config.read_properties(path) == {
        "group.id": "fraud-decisioning-engine",
        "session.timeout.ms": "45000",
    }


def test_read_properties_rejects_a_line_without_a_value(tmp_path: Path):
    path = tmp_path / "consumer.properties"
    path.write_text("group.id\n")
    with pytest.raises(config.ConfigError, match="consumer.properties:1"):
        config.read_properties(path)


def test_from_env_requires_bootstrap_and_registry():
    with pytest.raises(config.ConfigError, match="KAFKA_BOOTSTRAP_SERVERS"):
        config.from_env({"SCHEMA_REGISTRY_URL": "http://registry:8081"})


def test_defaults_match_the_production_topology():
    settings = config.from_env(ENV)
    consumer = settings.consumer_config()
    assert consumer["group.id"] == "fraud-decisioning-engine"
    assert consumer["auto.offset.reset"] == "earliest"
    assert consumer["enable.auto.commit"] == "false"
    assert settings.input_topic == "cards.authorisation.requested.v1"
    assert settings.ledger_topic == "cards.ledger.posted.v1"
    assert settings.reader_schema_path.name == "cards_authorisation_requested_v1.avsc"
    assert settings.reader_schema_path.exists()
    assert settings.ledger_schema_path.exists()


def test_mounted_properties_override_the_defaults(tmp_path: Path):
    path = tmp_path / "consumer.properties"
    path.write_text("session.timeout.ms=45000\nmax.poll.interval.ms=300000\n")
    settings = config.from_env({**ENV, "KAFKA_CONSUMER_PROPERTIES": str(path)})
    consumer = settings.consumer_config()
    assert consumer["session.timeout.ms"] == "45000"
    assert consumer["max.poll.interval.ms"] == "300000"
    assert consumer["bootstrap.servers"] == "broker-1:9092"


def test_auto_commit_is_refused():
    settings = config.Settings(
        bootstrap_servers="broker-1:9092",
        schema_registry_url="http://registry:8081",
        consumer_properties={"enable.auto.commit": "true"},
    )
    with pytest.raises(config.ConfigError, match="enable.auto.commit"):
        settings.consumer_config()


def test_producer_waits_for_all_replicas():
    producer = config.from_env(ENV).producer_config()
    assert producer["acks"] == "all"
    assert producer["enable.idempotence"] == "true"


def test_numeric_settings_are_validated():
    with pytest.raises(config.ConfigError, match="BATCH_SIZE"):
        config.from_env({**ENV, "BATCH_SIZE": "lots"})
    assert config.from_env({**ENV, "BATCH_SIZE": "250"}).batch_size == 250
