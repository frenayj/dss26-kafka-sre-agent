package com.dss26.cards.txnhistory.history

import com.dss26.payments.CardAuthEvent
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.Instant
import java.util.Currency

enum class TransactionStatus { PENDING, REVERSED, SETTLED }

data class CardTransaction(
    val authId: String,
    val cardToken: String,
    val merchantId: String,
    val amount: BigDecimal,
    val currency: String,
    val merchantCountry: String,
    val channel: String,
    val status: TransactionStatus,
    val authorisedAt: Instant,
    val sourcePartition: Int,
    val sourceOffset: Long,
)

/**
 * Maps one authorisation request to a history row. Amounts arrive as a double
 * in major units; we store them at the currency's minor-unit scale so the apps
 * never render 12.300000001.
 */
fun CardAuthEvent.toCardTransaction(partition: Int, offset: Long): CardTransaction {
    val scale = runCatching { Currency.getInstance(currency).defaultFractionDigits }
        .getOrDefault(2)
        .coerceAtLeast(0)
    return CardTransaction(
        authId = authId,
        cardToken = cardToken,
        merchantId = merchantId,
        amount = BigDecimal.valueOf(amount).setScale(scale, RoundingMode.HALF_EVEN),
        currency = currency,
        merchantCountry = country,
        channel = channel,
        status = TransactionStatus.PENDING,
        authorisedAt = ts,
        sourcePartition = partition,
        sourceOffset = offset,
    )
}
