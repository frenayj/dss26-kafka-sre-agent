package com.dss26.cards.lifecycle.risk

import com.dss26.cards.events.BlockInitiator
import com.dss26.cards.events.BlockReason
import com.dss26.cards.lifecycle.card.CardService
import com.dss26.risk.events.LimitType
import com.dss26.risk.events.RiskLimitBreached
import org.slf4j.LoggerFactory
import org.springframework.kafka.annotation.KafkaListener
import org.springframework.stereotype.Component

/**
 * Auto-blocks a card when the risk engine reports a breach that warrants it.
 * Velocity breaches only alert the cardholder (cardholder-alerts); blocking on
 * them froze too many legitimate cards.
 */
@Component
class RiskLimitListener(private val cards: CardService) {
    private val log = LoggerFactory.getLogger(javaClass)

    @KafkaListener(id = "risk-limits", topics = ["risk.limit.breached.v1"], groupId = "card-lifecycle-svc")
    fun onRiskLimitBreached(breach: RiskLimitBreached) {
        if (breach.limitType !in AUTO_BLOCK) return
        log.info("Blocking {} after {} breach", breach.cardToken, breach.limitType)
        cards.block(breach.cardToken, BlockReason.FRAUD_SUSPECTED, BlockInitiator.SYSTEM)
    }

    companion object {
        val AUTO_BLOCK = setOf(LimitType.EXPOSURE, LimitType.MCC_RESTRICTED)
    }
}
