package com.dss26.cards.lifecycle.events

import com.dss26.cards.events.CardActivated
import com.dss26.cards.events.CardBlocked
import com.dss26.cards.events.CardIssued
import com.dss26.cards.events.CardReplaced
import org.apache.avro.Schema
import org.apache.avro.specific.SpecificRecord

object CardTopics {
    private val bySchema: Map<String, Pair<String, Schema>> = mapOf(
        CardIssued.getClassSchema().fullName to ("cards.card.issued.v1" to CardIssued.getClassSchema()),
        CardActivated.getClassSchema().fullName to ("cards.card.activated.v1" to CardActivated.getClassSchema()),
        CardBlocked.getClassSchema().fullName to ("cards.card.blocked.v1" to CardBlocked.getClassSchema()),
        CardReplaced.getClassSchema().fullName to ("cards.card.replaced.v1" to CardReplaced.getClassSchema()),
    )

    fun topicFor(record: SpecificRecord): String =
        bySchema[record.schema.fullName]?.first ?: error("No topic for ${record.schema.fullName}")

    fun schemaFor(eventType: String): Schema =
        bySchema[eventType]?.second ?: error("Unknown event type $eventType")
}
