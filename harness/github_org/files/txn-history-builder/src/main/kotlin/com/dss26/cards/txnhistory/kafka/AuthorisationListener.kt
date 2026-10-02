package com.dss26.cards.txnhistory.kafka

import com.dss26.cards.txnhistory.history.CardTransactionRepository
import com.dss26.cards.txnhistory.history.TxnHistoryProperties
import com.dss26.cards.txnhistory.history.toCardTransaction
import com.dss26.payments.CardAuthEvent
import io.micrometer.core.instrument.MeterRegistry
import org.apache.kafka.clients.consumer.ConsumerRecord
import org.slf4j.LoggerFactory
import org.springframework.kafka.annotation.KafkaListener
import org.springframework.kafka.listener.BatchListenerFailedException
import org.springframework.stereotype.Component

@Component
class AuthorisationListener(
    private val repository: CardTransactionRepository,
    private val properties: TxnHistoryProperties,
    meterRegistry: MeterRegistry,
) {
    private val log = LoggerFactory.getLogger(javaClass)
    private val written = meterRegistry.counter("txn_history.transactions.written")
    private val ignoredTier = meterRegistry.counter("txn_history.transactions.ignored", "reason", "tier")
    private val batchSize = meterRegistry.summary("txn_history.batch.size")

    @KafkaListener(id = "authorisations", topics = ["\${txn-history.topic}"])
    fun onAuthorisations(records: List<ConsumerRecord<String, CardAuthEvent?>>) {
        batchSize.record(records.size.toDouble())
        val transactions = records.mapIndexedNotNull { index, record ->
            // ErrorHandlingDeserializer leaves the value null when the payload
            // could not be read; hand that record to the error handler.
            val auth = record.value()
                ?: throw BatchListenerFailedException(
                    "Unreadable value at ${record.topic()}-${record.partition()}@${record.offset()}",
                    index,
                )
            if (auth.tier !in properties.acceptedTiers) {
                ignoredTier.increment()
                null
            } else {
                auth.toCardTransaction(record.partition(), record.offset())
            }
        }
        if (transactions.isEmpty()) return
        repository.upsertAll(transactions)
        written.increment(transactions.size.toDouble())
        log.debug("Wrote {} of {} authorisations", transactions.size, records.size)
    }
}
