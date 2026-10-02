package com.dss26.cards.txnhistory.api

import com.dss26.cards.txnhistory.history.CardTransaction
import com.dss26.cards.txnhistory.history.CardTransactionRepository
import org.springframework.format.annotation.DateTimeFormat
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.time.Instant

data class TransactionPage(val items: List<CardTransaction>, val nextBefore: Instant?)

@RestController
@RequestMapping("/v1")
class TransactionHistoryController(private val repository: CardTransactionRepository) {

    @GetMapping("/cards/{cardToken}/transactions")
    fun list(
        @PathVariable cardToken: String,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) before: Instant?,
        @RequestParam(defaultValue = "50") limit: Int,
    ): TransactionPage {
        val pageSize = limit.coerceIn(1, 200)
        val items = repository.findByCard(cardToken, before, pageSize)
        val next = if (items.size == pageSize) items.last().authorisedAt else null
        return TransactionPage(items, next)
    }

    /** Used by fraud-case-management to find the card behind a scored authorisation. */
    @GetMapping("/transactions/{authId}")
    fun byAuthId(@PathVariable authId: String): ResponseEntity<CardTransaction> =
        repository.findByAuthId(authId)?.let { ResponseEntity.ok(it) } ?: ResponseEntity.notFound().build()
}
