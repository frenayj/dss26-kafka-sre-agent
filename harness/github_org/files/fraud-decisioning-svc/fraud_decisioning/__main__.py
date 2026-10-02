"""Entry point: ``python -m fraud_decisioning``."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading

from confluent_kafka import Consumer, Producer
from confluent_kafka.schema_registry import SchemaRegistryClient

from fraud_decisioning import __version__, config, metrics, runtime, schemas
from fraud_decisioning.consumer import DecisionLoop, LedgerDeliveryError
from fraud_decisioning.serde import avro_reader, avro_writer

log = logging.getLogger("fraud_decisioning")


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-5s [fraud-decisioning] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    settings = config.from_env()
    reader_schema = schemas.load(settings.reader_schema_path)
    ledger_schema = schemas.load(settings.ledger_schema_path)

    registry = SchemaRegistryClient({"url": settings.schema_registry_url})
    consumer = Consumer(settings.consumer_config())
    producer = Producer(settings.producer_config())
    loop = DecisionLoop(
        consumer,
        producer,
        deserialise=avro_reader(registry, reader_schema),
        serialise=avro_writer(registry, ledger_schema, settings.ledger_topic),
        ledger_topic=settings.ledger_topic,
        batch_size=settings.batch_size,
        poll_timeout_s=settings.poll_timeout_s,
        blocked_retry_s=settings.blocked_retry_s,
        flush_timeout_s=settings.ledger_flush_timeout_s,
    )
    consumer.subscribe(
        [settings.input_topic],
        on_revoke=lambda _consumer, partitions: loop.forget(partitions),
    )

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    metrics.serve(settings.metrics_port)
    log.info(
        "fraud-decisioning-svc %s | group=%s in=%s out=%s reader=%s",
        __version__, settings.group_id, settings.input_topic, settings.ledger_topic,
        settings.reader_schema_path.name,
    )
    runtime.tune_gc()
    try:
        loop.run(stop.is_set)
    except LedgerDeliveryError:
        log.critical("ledger postings not acknowledged; exiting so the pod restarts", exc_info=True)
        return 2
    finally:
        producer.flush(10)
        consumer.close()
    log.info("stopped cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
