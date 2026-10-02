package com.dss26.cards.txnhistory.history

import com.dss26.payments.CardAuthEvent
import org.junit.jupiter.api.Test
import java.math.BigDecimal
import java.time.Instant
import kotlin.test.assertEquals

class CardTransactionMapperTest {

    private fun auth(amount: Double, currency: String) = CardAuthEvent.newBuilder()
        .setAuthId("4d1f6c1e-2b7a-4a0e-9c55-0f3f1f2b9a10")
        .setCardToken("tok_5f2b8c")
        .setMerchantId("MRC-0042817")
        .setAmount(amount)
        .setCurrency(currency)
        .setCountry("FR")
        .setTs(Instant.parse("2026-03-02T09:15:30Z"))
        .setChannel("CARD_PRESENT")
        .setTier("prod")
        .build()

    @Test
    fun `stores euro amounts with two decimals`() {
        val tx = auth(12.3, "EUR").toCardTransaction(partition = 4, offset = 99L)
        assertEquals(BigDecimal("12.30"), tx.amount)
        assertEquals(TransactionStatus.PENDING, tx.status)
        assertEquals(4, tx.sourcePartition)
    }

    @Test
    fun `stores yen amounts without decimals`() {
        val tx = auth(1530.0, "JPY").toCardTransaction(partition = 0, offset = 1L)
        assertEquals(BigDecimal("1530"), tx.amount)
    }

    @Test
    fun `keeps merchant country and channel for the detail screen`() {
        val tx = auth(5.0, "EUR").toCardTransaction(partition = 0, offset = 1L)
        assertEquals("FR", tx.merchantCountry)
        assertEquals("CARD_PRESENT", tx.channel)
    }
}
