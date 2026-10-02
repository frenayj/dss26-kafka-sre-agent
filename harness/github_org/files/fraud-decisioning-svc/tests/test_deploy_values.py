"""Guards on the consumer settings we deploy (deploy/helm/values-*.yaml)."""

from pathlib import Path

import pytest
import yaml

DEPLOY = Path(__file__).resolve().parent.parent / "deploy" / "helm"
VALUES = sorted(DEPLOY.glob("values-*.yaml"))


def consumer_settings(path: Path) -> dict:
    return yaml.safe_load(path.read_text())["kafka"]["consumer"]


def test_every_environment_has_values():
    assert {p.name for p in VALUES} >= {"values-prod.yaml", "values-uat.yaml"}


@pytest.mark.parametrize("path", VALUES, ids=lambda p: p.name)
def test_group_id_is_the_post_adr_0011_group(path):
    assert consumer_settings(path)["group.id"] == "fraud-decisioning-engine"


@pytest.mark.parametrize("path", VALUES, ids=lambda p: p.name)
def test_offsets_are_committed_by_the_service(path):
    assert consumer_settings(path)["enable.auto.commit"] is False


@pytest.mark.parametrize("path", VALUES, ids=lambda p: p.name)
def test_heartbeat_fits_the_session_timeout(path):
    consumer = consumer_settings(path)
    assert consumer["heartbeat.interval.ms"] * 3 <= consumer["session.timeout.ms"]


@pytest.mark.parametrize("path", VALUES, ids=lambda p: p.name)
def test_max_poll_interval_stays_raised(path):
    # INC-2025-03-18-002: 30 s evicted members during long GC pauses.
    assert consumer_settings(path)["max.poll.interval.ms"] >= 300000
