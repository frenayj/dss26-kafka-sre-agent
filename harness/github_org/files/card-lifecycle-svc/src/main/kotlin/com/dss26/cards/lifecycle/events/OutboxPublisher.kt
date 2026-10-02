package com.dss26.cards.lifecycle.events

import org.apache.avro.specific.SpecificRecord
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.annotation.Transactional
import java.util.concurrent.TimeUnit

/**
 * Drains the outbox in id order. Keyed by card token, so every event for one
 * card lands on the same partition in the order it happened.
 */
@Component
class OutboxPublisher(
    private val outbox: Outbox,
    private val kafka: KafkaTemplate<String, SpecificRecord>,
) {

    @Scheduled(fixedDelay = 200)
    @Transactional
    fun drain() {
        val batch = outbox.pending(limit = 500)
        if (batch.isEmpty()) return
        val sends = batch.map { kafka.send(it.topic, it.key, it.record) }
        sends.forEach { it.get(10, TimeUnit.SECONDS) }
        outbox.markPublished(batch.map { it.id })
    }
}
