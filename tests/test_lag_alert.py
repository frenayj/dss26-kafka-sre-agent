"""The consumer-lag page carries the lag measured on the cluster, and every
place the agent can read the monitor's threshold agrees on it."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from harness import scenarios
from harness.pagerduty import lag_alert
from harness.stubs._kb_pages import PAGES

REPO_ROOT = Path(__file__).resolve().parent.parent
TOPIC = "cards.authorisation.requested.v1"

DESCRIBE = """
GROUP                    TOPIC                            PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG   CONSUMER-ID  HOST        CLIENT-ID
fraud-decisioning-engine cards.authorisation.requested.v1 0          3078            9310            6232  rdkafka-1    /172.21.0.7 rdkafka
fraud-decisioning-engine cards.authorisation.requested.v1 1          100             150             50    rdkafka-1    /172.21.0.7 rdkafka
fraud-decisioning-engine cards.ledger.posted.v1           0          -               3078            -     -            -           -
"""


def _details():
    return scenarios.load("consumer-lag").incident()["incident"]["custom_details"]


def test_parse_lag_sums_the_topics_partitions():
    assert lag_alert.parse_lag(DESCRIBE, TOPIC) == 6282
    assert lag_alert.parse_lag(DESCRIBE, "cards.ledger.posted.v1") is None
    assert lag_alert.parse_lag("Error: group not found", TOPIC) is None


def test_measure_waits_for_the_threshold_and_reports_the_lag():
    readings = iter([None, 3_100, 6_282])
    clock = iter([0, 1, 3, 5, 5])
    measured = lag_alert.measure(
        _details(),
        read_lag=lambda group, topic: next(readings),
        sleep=lambda s: None,
        now=lambda: next(clock),
        log=lambda line: None,
    )
    assert measured["metric_value"] == 6_282
    assert measured["snapshot_url"].endswith("?to_ts=5000")
    message = lag_alert.alert_message(measured)
    assert "Last evaluated value: 6,282 (threshold 5,000)" in message


def test_measure_gives_up_when_the_lag_never_passes_the_threshold():
    clock = iter(range(0, 1000, 60))
    with pytest.raises(RuntimeError, match="still not above the 5,000 threshold"):
        lag_alert.measure(
            _details(),
            read_lag=lambda group, topic: 2,
            wait_s=120,
            sleep=lambda s: None,
            now=lambda: next(clock),
            log=lambda line: None,
        )


def test_the_fixture_alert_is_self_consistent():
    inc = scenarios.load("consumer-lag").incident()["incident"]
    details = inc["custom_details"]
    assert inc["body"]["details"] == lag_alert.alert_message(details)
    assert details["metric_value"] > details["threshold_critical"]
    assert details["monitor_query"].endswith(f"> {details['threshold_critical']}")


def test_alert_monitor_code_and_knowledge_base_agree_on_the_threshold():
    threshold = _details()["threshold_critical"]
    snapshot = json.loads((REPO_ROOT / "harness/stubs/data/github-dss26-org.json").read_text())
    repos = snapshot["repos"] if isinstance(snapshot["repos"], list) else snapshot["repos"].values()
    repo = next(r for r in repos if r["name"] == "fraud-decisioning-svc")
    monitors = repo["files"]["monitoring/monitors.tf"]["text"]
    assert re.search(r"critical\s+=\s+(\d+)", monitors).group(1) == str(threshold)
    assert f"above {threshold:,} records of lag" in repo["files"]["README.md"]["text"]
    service = next(p for p in PAGES if p.title == "Service: fraud-decisioning-svc")
    assert f"critical above {threshold:,}." in service.body()
