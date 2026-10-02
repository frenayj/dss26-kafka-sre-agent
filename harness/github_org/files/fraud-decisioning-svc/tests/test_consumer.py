import json

import pytest

from fraud_decisioning.consumer import DecisionLoop, LedgerDeliveryError, writer_schema_id
from fraud_decisioning.ledger import posting_id_for

TOPIC = "cards.authorisation.requested.v1"


class Record:
    def __init__(self, partition, offset, value, topic=TOPIC):
        self._topic, self._partition, self._offset, self._value = topic, partition, offset, value

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset

    def value(self):
        return self._value

    def error(self):
        return None


class ScriptedConsumer:
    """Hands out pre-built batches and records what the loop asked of it."""

    def __init__(self, *batches):
        self.batches = list(batches)
        self.commits, self.paused, self.resumed, self.seeks = [], [], [], []

    def consume(self, num_messages, timeout):
        return self.batches.pop(0) if self.batches else []

    def commit(self, offsets, asynchronous):
        assert asynchronous is False
        self.commits.append(sorted((tp.partition, tp.offset) for tp in offsets))

    def pause(self, partitions):
        self.paused.extend(tp.partition for tp in partitions)

    def resume(self, partitions):
        self.resumed.extend(tp.partition for tp in partitions)

    def seek(self, tp):
        self.seeks.append((tp.partition, tp.offset))


class RecordingProducer:
    def __init__(self, reject=False):
        self.reject = reject
        self.produced = []
        self._callbacks = []

    def produce(self, topic, key, value, on_delivery):
        self.produced.append((topic, key, json.loads(value)))
        self._callbacks.append(on_delivery)

    def poll(self, timeout):
        return 0

    def flush(self, timeout):
        for cb in self._callbacks:
            cb("broker rejected the record" if self.reject else None, None)
        self._callbacks.clear()
        return 0


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def auth_bytes(auth_id, amount=25.0):
    return json.dumps(
        {
            "auth_id": auth_id,
            "merchant_id": "mch_77",
            "amount": amount,
            "currency": "EUR",
            "country": "NL",
            "channel": "CARD_PRESENT",
            "risk_signals": [],
        }
    ).encode()


UNREADABLE = b"\x00\x00\x00\x00\x2a\x0aoops"


def read_json(msg):
    return json.loads(msg.value())


def make_loop(consumer, producer, clock=None, deserialise=read_json):
    return DecisionLoop(
        consumer,
        producer,
        deserialise=deserialise,
        serialise=lambda posting: json.dumps(posting).encode(),
        ledger_topic="cards.ledger.posted.v1",
        batch_size=500,
        blocked_retry_s=5.0,
        clock=clock or Clock(),
        now_ms=lambda: 1758270000000,
    )


def test_posts_every_record_then_commits_the_next_offset_per_partition():
    consumer = ScriptedConsumer(
        [
            Record(0, 10, auth_bytes("a")),
            Record(1, 4, auth_bytes("b")),
            Record(0, 11, auth_bytes("c")),
        ]
    )
    producer = RecordingProducer()

    assert make_loop(consumer, producer).run_once() == 3

    assert [p[2]["auth_id"] for p in producer.produced] == ["a", "b", "c"]
    assert producer.produced[0][1] == b"a"
    assert producer.produced[0][2]["posting_id"] == posting_id_for("a")
    assert consumer.commits == [[(0, 12), (1, 5)]]


def test_unreadable_record_holds_its_partition_and_nothing_past_it_is_committed():
    consumer = ScriptedConsumer(
        [
            Record(0, 10, auth_bytes("a")),
            Record(0, 11, UNREADABLE),
            Record(0, 12, auth_bytes("c")),  # prefetched behind the bad record
            Record(1, 4, auth_bytes("b")),
        ]
    )
    producer = RecordingProducer()
    loop = make_loop(consumer, producer)

    assert loop.run_once() == 2

    assert [p[2]["auth_id"] for p in producer.produced] == ["a", "b"]
    assert consumer.commits == [[(0, 11), (1, 5)]]
    assert consumer.paused == [0]
    assert loop.held == {(TOPIC, 0): 11}


def test_held_partition_is_retried_from_the_same_offset_after_the_backoff():
    clock = Clock()
    consumer = ScriptedConsumer([Record(0, 11, UNREADABLE)], [], [Record(0, 11, UNREADABLE)])
    loop = make_loop(consumer, RecordingProducer(), clock=clock)

    loop.run_once()
    clock.now = 1.0
    loop.run_once()
    assert consumer.seeks == []  # still backing off

    clock.now = 6.0
    loop.run_once()
    assert consumer.seeks == [(0, 11)]
    assert consumer.resumed == [0]
    assert consumer.paused == [0, 0]  # failed again, paused again
    assert consumer.commits == []
    assert loop.held == {(TOPIC, 0): 11}


def test_partition_flows_again_once_the_record_is_readable():
    clock = Clock()
    readable = {"now": False}

    def deserialise(msg):
        if msg.value() == UNREADABLE and not readable["now"]:
            raise ValueError("Schema mismatch")
        return json.loads(auth_bytes("x")) if msg.value() == UNREADABLE else read_json(msg)

    consumer = ScriptedConsumer([Record(0, 11, UNREADABLE)], [Record(0, 11, UNREADABLE)])
    loop = make_loop(consumer, RecordingProducer(), clock=clock, deserialise=deserialise)

    loop.run_once()
    readable["now"] = True
    clock.now = 10.0
    assert loop.run_once() == 1
    assert loop.held == {}
    assert consumer.commits == [[(0, 12)]]


def test_rejected_ledger_posting_commits_nothing():
    consumer = ScriptedConsumer([Record(0, 10, auth_bytes("a"))])
    with pytest.raises(LedgerDeliveryError):
        make_loop(consumer, RecordingProducer(reject=True)).run_once()
    assert consumer.commits == []


def test_revoked_partitions_are_forgotten():
    class TP:
        topic, partition = TOPIC, 0

    consumer = ScriptedConsumer([Record(0, 11, UNREADABLE)])
    loop = make_loop(consumer, RecordingProducer())
    loop.run_once()
    loop.forget([TP()])
    assert loop.held == {}


def test_writer_schema_id_from_the_wire_format_header():
    assert writer_schema_id(b"\x00\x00\x00\x01\x07rest") == 263
    assert writer_schema_id(b"{}") is None
    assert writer_schema_id(None) is None
