"""Prometheus metrics, served on METRICS_PORT (default 9102)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server

DECISIONS = Counter(
    "fraud_decisioning_decisions",
    "Authorisations decided, by outcome.",
    ["outcome"],
)
POSTINGS = Counter(
    "fraud_decisioning_ledger_postings",
    "Ledger postings acknowledged by the brokers.",
)
POSTING_ERRORS = Counter(
    "fraud_decisioning_ledger_posting_errors",
    "Ledger postings rejected or not acknowledged in time.",
)
BATCH_SECONDS = Histogram(
    "fraud_decisioning_batch_seconds",
    "Time to decide, post and commit one batch.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
DESERIALISATION_ERRORS = Counter(
    "fraud_decisioning_deserialisation_errors",
    "Records the pinned reader schema could not read, by partition.",
    ["partition"],
)
BLOCKED_PARTITIONS = Gauge(
    "fraud_decisioning_blocked_partitions",
    "Partitions held at a record that cannot be read.",
)


def serve(port: int) -> None:
    start_http_server(port)
