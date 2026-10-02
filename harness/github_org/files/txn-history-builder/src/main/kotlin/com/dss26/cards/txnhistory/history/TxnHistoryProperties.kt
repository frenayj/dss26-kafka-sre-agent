package com.dss26.cards.txnhistory.history

import org.springframework.boot.context.properties.ConfigurationProperties

@ConfigurationProperties("txn-history")
data class TxnHistoryProperties(
    /** Source topic. Overridable so a replay can read from a restored copy. */
    val topic: String = "cards.authorisation.requested.v1",
    /** Producer `tier` values that may reach the table. */
    val acceptedTiers: Set<String> = setOf("prod"),
)
