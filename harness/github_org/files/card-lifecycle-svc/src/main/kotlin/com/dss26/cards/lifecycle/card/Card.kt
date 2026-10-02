package com.dss26.cards.lifecycle.card

import com.dss26.cards.events.BlockReason
import com.dss26.cards.events.CardFormFactor
import java.time.Instant

data class Card(
    val cardToken: String,
    val customerId: String,
    val productCode: String,
    val formFactor: CardFormFactor,
    val bin: String,
    val expiryYyyymm: String,
    val state: CardState,
    val blockReason: BlockReason?,
    val updatedAt: Instant,
)
