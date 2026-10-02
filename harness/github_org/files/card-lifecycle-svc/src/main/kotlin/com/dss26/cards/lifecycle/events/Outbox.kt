package com.dss26.cards.lifecycle.events

import org.apache.avro.specific.SpecificDatumReader
import org.apache.avro.specific.SpecificDatumWriter
import org.apache.avro.specific.SpecificRecord
import org.apache.avro.io.DecoderFactory
import org.apache.avro.io.EncoderFactory
import org.springframework.jdbc.core.simple.JdbcClient
import org.springframework.stereotype.Component
import java.io.ByteArrayOutputStream

/**
 * Transactional outbox: events are written in the same transaction as the card
 * row and published by [OutboxPublisher]. Payloads are stored in Avro's JSON
 * encoding so they stay readable in psql during an incident.
 */
@Component
class Outbox(private val jdbc: JdbcClient) {

    data class Entry(val id: Long, val topic: String, val key: String, val record: SpecificRecord)

    fun add(key: String, record: SpecificRecord) {
        val topic = CardTopics.topicFor(record)
        val out = ByteArrayOutputStream()
        val encoder = EncoderFactory.get().jsonEncoder(record.schema, out)
        SpecificDatumWriter<SpecificRecord>(record.schema).write(record, encoder)
        encoder.flush()
        jdbc.sql("INSERT INTO outbox (topic, event_key, event_type, payload) VALUES (:topic, :key, :type, CAST(:payload AS jsonb))")
            .param("topic", topic)
            .param("key", key)
            .param("type", record.schema.fullName)
            .param("payload", out.toString(Charsets.UTF_8))
            .update()
    }

    fun pending(limit: Int): List<Entry> =
        jdbc.sql("SELECT id, topic, event_key, event_type, payload::text AS payload FROM outbox WHERE published_at IS NULL ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED")
            .param("limit", limit)
            .query { rs, _ ->
                val schema = CardTopics.schemaFor(rs.getString("event_type"))
                val decoder = DecoderFactory.get().jsonDecoder(schema, rs.getString("payload"))
                val record = SpecificDatumReader<SpecificRecord>(schema).read(null, decoder)
                Entry(rs.getLong("id"), rs.getString("topic"), rs.getString("event_key"), record)
            }
            .list()

    fun markPublished(ids: List<Long>) {
        if (ids.isEmpty()) return
        jdbc.sql("UPDATE outbox SET published_at = now() WHERE id IN (:ids)")
            .param("ids", ids)
            .update()
    }
}
