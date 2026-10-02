"""Avro (de)serialisation through the Schema Registry.

The reader schema for cards.authorisation.requested.v1 is pinned: records are
resolved from whatever writer schema the producer registered onto the schema
in ``schemas/``. A writer schema that cannot be resolved onto it raises, and
the decisioning loop holds the partition.
"""

from __future__ import annotations

from typing import Any

from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext


class EmptyRecordError(ValueError):
    """A null value on a topic where every record must carry an authorisation."""


def avro_reader(registry: SchemaRegistryClient, reader_schema: str):
    deserializer = AvroDeserializer(registry, schema_str=reader_schema)

    def deserialise(msg: Any) -> dict[str, Any]:
        value = deserializer(msg.value(), SerializationContext(msg.topic(), MessageField.VALUE))
        if value is None:
            raise EmptyRecordError(f"null value at {msg.topic()}[{msg.partition()}]@{msg.offset()}")
        return value

    return deserialise


def avro_writer(registry: SchemaRegistryClient, schema: str, topic: str):
    serializer = AvroSerializer(registry, schema)
    ctx = SerializationContext(topic, MessageField.VALUE)

    def serialise(record: dict[str, Any]) -> bytes:
        return serializer(record, ctx)

    return serialise
