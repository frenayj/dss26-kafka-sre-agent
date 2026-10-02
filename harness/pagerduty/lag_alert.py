"""The consumer-lag alert's value, measured on the cluster when the page goes out.

A real Datadog monitor reports the lag it last evaluated. The scenario's
incident.json carries fixed numbers for stub mode; a live page replaces them
with the lag Kafka reports now, so the agent finds the same figure in the
alert and in Lenses (and later readings only higher, as the lag grows).

Stdlib only, like pagerduty_demo.py, and free of import-time side effects so
the tests can load it.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any, Callable, Dict, Optional

# The broker container, reached the way reset.sh reaches it.
BROKER_CONTAINER = "demo-kafka-prod"
# How long to wait for the lag to pass the threshold before giving up: the
# monitor would not have fired, and paging anyway would contradict the alert.
WAIT_S = 120
POLL_S = 2


def parse_lag(describe: str, topic: str) -> Optional[int]:
    """Total of the LAG column of ``kafka-consumer-groups --describe`` for ``topic``.

    None when no partition of ``topic`` has a lag (no committed offset yet, or
    the group is unknown).
    """
    rows = [line.split() for line in describe.splitlines() if line.strip()]
    header = next((r for r in rows if "TOPIC" in r and "LAG" in r), None)
    if header is None:
        return None
    topic_col, lag_col = header.index("TOPIC"), header.index("LAG")
    lags = [
        int(r[lag_col])
        for r in rows
        if r is not header and len(r) > lag_col and r[topic_col] == topic and r[lag_col].isdigit()
    ]
    return sum(lags) if lags else None


def consumer_lag(group: str, topic: str) -> Optional[int]:
    """The group's lag on ``topic`` now, read from the broker."""
    try:
        out = subprocess.run(
            [
                "docker", "exec", BROKER_CONTAINER,
                "kafka-consumer-groups", "--bootstrap-server", "localhost:9092",
                "--describe", "--group", group,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_lag(out.stdout, topic)


def alert_message(details: Dict[str, Any]) -> str:
    """The alert body Datadog writes, from the monitor's details.

    incident.json's ``body.details`` is this text for its own numbers (a test
    keeps the two in step).
    """
    return (
        f"Datadog monitor `{details['monitor_name']}` (id {details['monitor_id']}) entered "
        f"CRITICAL state. Query: `{details['monitor_query']}`. Last evaluated value: "
        f"{details['metric_value']:,} (threshold {details['threshold_critical']:,}). "
        f"See snapshot: {details['snapshot_url']}"
    )


def measure(
    details: Dict[str, Any],
    *,
    read_lag: Callable[[str, str], Optional[int]] = consumer_lag,
    wait_s: float = WAIT_S,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
    log: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """``details`` with the measured lag as the monitor's last evaluated value.

    Waits until the lag passes ``threshold_critical``; raises RuntimeError if
    it has not after ``wait_s`` (is the scenario induced?).
    """
    tags = dict(t.split(":", 1) for t in details.get("tags", []) if ":" in t)
    group, topic = tags["consumer_group"], tags["topic"]
    threshold = int(details["threshold_critical"])
    deadline = now() + wait_s
    while True:
        lag = read_lag(group, topic)
        if lag is not None and lag > threshold:
            break
        if now() >= deadline:
            raise RuntimeError(
                f"{group} lag on {topic} is {lag if lag is not None else 'unknown'}, still not "
                f"above the {threshold:,} threshold after {wait_s:.0f}s - is the scenario induced?"
            )
        log(f"[page] {group} lag {lag if lag is not None else '?'} - waiting for it to pass {threshold:,}...")
        sleep(POLL_S)
    snapshot = f"{details['alert_link']}?to_ts={int(now() * 1000)}"
    return {**details, "metric_value": lag, "snapshot_url": snapshot}
