import pytest

from fraud_cases.config import CONSUMER_GROUP, Settings

ENV = {
    "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
    "SCHEMA_REGISTRY_URL": "http://localhost:8081",
    "FRAUD_CASES_DB_URL": "postgresql://fraud_cases@localhost/fraud_cases",
}


def test_consumer_commits_manually_as_its_own_group():
    conf = Settings.from_env(ENV).consumer_config()
    assert conf["group.id"] == CONSUMER_GROUP == "fraud-case-management"
    assert conf["enable.auto.commit"] is False
    assert conf["partition.assignment.strategy"] == "cooperative-sticky"


def test_sasl_settings_only_when_sasl_is_used():
    sasl = Settings.from_env({**ENV, "KAFKA_USERNAME": "fraud-case-management", "KAFKA_PASSWORD": "x"})
    assert sasl.consumer_config()["sasl.mechanisms"] == "SCRAM-SHA-512"
    plain = Settings.from_env({**ENV, "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT"})
    assert "sasl.mechanisms" not in plain.consumer_config()


def test_missing_bootstrap_servers_fails_fast():
    with pytest.raises(RuntimeError, match="KAFKA_BOOTSTRAP_SERVERS"):
        Settings.from_env({k: v for k, v in ENV.items() if k != "KAFKA_BOOTSTRAP_SERVERS"})


def test_review_threshold_is_configurable():
    assert Settings.from_env({**ENV, "FRAUD_CASES_REVIEW_THRESHOLD": "0.65"}).review_threshold == 0.65
