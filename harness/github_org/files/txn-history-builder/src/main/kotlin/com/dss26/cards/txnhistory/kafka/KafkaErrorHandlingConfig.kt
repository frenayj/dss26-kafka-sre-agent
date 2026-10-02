package com.dss26.cards.txnhistory.kafka

import io.micrometer.core.instrument.MeterRegistry
import org.slf4j.LoggerFactory
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.kafka.listener.ConsumerRecordRecoverer
import org.springframework.kafka.listener.DefaultErrorHandler
import org.springframework.util.backoff.FixedBackOff

/**
 * A record we cannot read is not worth stopping a partition for: the
 * transaction still reaches the cardholder's statement through clearing.
 * Retry twice, then log, count and move on.
 */
@Configuration
class KafkaErrorHandlingConfig {
    private val log = LoggerFactory.getLogger(javaClass)

    @Bean
    fun kafkaErrorHandler(meterRegistry: MeterRegistry): DefaultErrorHandler {
        val skipped = meterRegistry.counter("txn_history.records.skipped")
        val recoverer = ConsumerRecordRecoverer { record, exception ->
            skipped.increment()
            log.error(
                "Skipping {}-{}@{} after retries: {}",
                record.topic(), record.partition(), record.offset(), exception.message,
            )
        }
        return DefaultErrorHandler(recoverer, FixedBackOff(1_000L, 2L))
    }
}
