"""The decisioning loop: read an authorisation, decide, post to the ledger, commit.

Two rules hold for every offset this loop commits:

* the ledger posting for the record has been acknowledged by the brokers, and
* no record before it on the same partition was skipped.

A record the pinned reader schema cannot read therefore holds its partition
(README, "Fail closed"). The partition is paused at that offset and retried
every ``blocked_retry_s`` seconds; the other partitions keep flowing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from confluent_kafka import KafkaError, KafkaException, TopicPartition

from fraud_decisioning import metrics
from fraud_decisioning.ledger import to_posting
from fraud_decisioning.scoring import assess

log = logging.getLogger(__name__)

Deserialise = Callable[[Any], dict[str, Any]]
Serialise = Callable[[dict[str, Any]], bytes]

# Log every attempt for the first few minutes of a hold, then once in a while.
_LOG_EVERY = 60


class LedgerDeliveryError(RuntimeError):
    """The brokers did not acknowledge every ledger posting of a batch.

    Nothing from the batch was committed. The process exits and restarts from
    the last committed offsets; postings are idempotent by posting_id.
    """


@dataclass
class _Hold:
    offset: int
    retry_at: float
    attempts: int = 1
    paused: bool = True


def writer_schema_id(value: bytes | None) -> int | None:
    """Schema Registry id from the wire-format header, if the record has one."""
    if value and len(value) >= 5 and value[0] == 0:
        return int.from_bytes(value[1:5], "big")
    return None


class DecisionLoop:
    def __init__(
        self,
        consumer: Any,
        producer: Any,
        *,
        deserialise: Deserialise,
        serialise: Serialise,
        ledger_topic: str,
        batch_size: int,
        poll_timeout_s: float = 1.0,
        blocked_retry_s: float = 5.0,
        flush_timeout_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        now_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._consumer = consumer
        self._producer = producer
        self._deserialise = deserialise
        self._serialise = serialise
        self._ledger_topic = ledger_topic
        self._batch_size = batch_size
        self._poll_timeout_s = poll_timeout_s
        self._blocked_retry_s = blocked_retry_s
        self._flush_timeout_s = flush_timeout_s
        self._clock = clock
        self._now_ms = now_ms
        self._holds: dict[tuple[str, int], _Hold] = {}

    @property
    def held(self) -> dict[tuple[str, int], int]:
        """(topic, partition) -> offset of the record that cannot be read."""
        return {tp: hold.offset for tp, hold in self._holds.items()}

    def run(self, should_stop: Callable[[], bool]) -> None:
        while not should_stop():
            self.run_once()

    def forget(self, partitions: Iterable[TopicPartition]) -> None:
        """Drop holds for partitions this member no longer owns (on revoke)."""
        for tp in partitions:
            self._holds.pop((tp.topic, tp.partition), None)
        metrics.BLOCKED_PARTITIONS.set(len(self._holds))

    def run_once(self) -> int:
        """One poll, decide, post and commit cycle. Returns records committed."""
        started = self._clock()
        self._retry_due(started)

        messages = self._consumer.consume(
            num_messages=self._batch_size, timeout=self._poll_timeout_s
        )
        if not messages:
            self._producer.poll(0)
            return 0

        failures: list[KafkaError] = []

        def on_delivery(err: KafkaError | None, _msg: Any) -> None:
            if err is not None:
                failures.append(err)

        to_commit: dict[tuple[str, int], int] = {}
        posted = 0
        for msg in messages:
            err = msg.error()
            if err is not None:
                if err.code() != KafkaError._PARTITION_EOF:
                    log.error("consumer error: %s", err)
                continue

            tp = (msg.topic(), msg.partition())
            hold = self._holds.get(tp)
            if hold is not None and hold.paused:
                # Prefetched behind a record we could not read.
                continue

            try:
                auth = self._deserialise(msg)
            except Exception as exc:  # any failure to read holds the partition
                self._hold(msg, exc)
                continue

            if hold is not None:
                log.info(
                    "%s[%d] readable again at offset %d after %d attempt(s)",
                    tp[0], tp[1], hold.offset, hold.attempts,
                )
                del self._holds[tp]
                metrics.BLOCKED_PARTITIONS.set(len(self._holds))

            assessment = assess(auth)
            posting = to_posting(auth, assessment, self._now_ms())
            self._producer.produce(
                self._ledger_topic,
                key=auth["auth_id"].encode(),
                value=self._serialise(posting),
                on_delivery=on_delivery,
            )
            self._producer.poll(0)
            metrics.DECISIONS.labels(assessment.outcome).inc()
            to_commit[tp] = msg.offset() + 1
            posted += 1

        if not to_commit:
            return 0

        unacked = self._producer.flush(self._flush_timeout_s)
        if failures or unacked:
            metrics.POSTING_ERRORS.inc(len(failures) + unacked)
            raise LedgerDeliveryError(
                f"{len(failures)} ledger posting(s) rejected and {unacked} not acknowledged "
                f"within {self._flush_timeout_s}s; no offsets committed"
                + (f" (first error: {failures[0]})" if failures else "")
            )

        offsets = [TopicPartition(t, p, o) for (t, p), o in to_commit.items()]
        try:
            self._consumer.commit(offsets=offsets, asynchronous=False)
        except KafkaException as exc:
            # Typically a rebalance in flight. The new owner re-reads from the
            # last committed offset; the postings it repeats carry the same
            # posting_id and are de-duplicated by the General Ledger.
            log.warning("commit failed, records will be re-read: %s", exc)
            return 0

        metrics.POSTINGS.inc(posted)
        metrics.BATCH_SECONDS.observe(self._clock() - started)
        return posted

    def _hold(self, msg: Any, exc: Exception) -> None:
        topic, partition, offset = msg.topic(), msg.partition(), msg.offset()
        key = (topic, partition)
        previous = self._holds.get(key)
        attempts = previous.attempts + 1 if previous and previous.offset == offset else 1
        self._holds[key] = _Hold(offset, self._clock() + self._blocked_retry_s, attempts)
        self._consumer.pause([TopicPartition(topic, partition)])

        metrics.DESERIALISATION_ERRORS.labels(str(partition)).inc()
        metrics.BLOCKED_PARTITIONS.set(len(self._holds))
        if attempts == 1 or attempts % _LOG_EVERY == 0:
            log.error(
                "cannot read %s[%d]@%d (writer schema id %s, attempt %d): %s: %s - "
                "holding the partition, nothing at or after this offset is committed",
                topic, partition, offset, writer_schema_id(msg.value()), attempts,
                type(exc).__name__, exc,
            )

    def _retry_due(self, now: float) -> None:
        for (topic, partition), hold in self._holds.items():
            if hold.paused and now >= hold.retry_at:
                self._consumer.seek(TopicPartition(topic, partition, hold.offset))
                self._consumer.resume([TopicPartition(topic, partition)])
                hold.paused = False
