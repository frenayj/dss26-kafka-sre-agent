package com.dss26.cards.txnhistory.history

import org.springframework.jdbc.core.RowMapper
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.stereotype.Repository
import java.sql.Timestamp
import java.time.Instant

@Repository
class CardTransactionRepository(private val jdbc: NamedParameterJdbcTemplate) {

    /** One JDBC batch per poll. Replays and rebalances are no-ops thanks to the PK. */
    fun upsertAll(transactions: List<CardTransaction>) {
        val params = transactions.map { it.toParams() }.toTypedArray()
        jdbc.batchUpdate(UPSERT, params)
    }

    fun findByCard(cardToken: String, before: Instant?, limit: Int): List<CardTransaction> =
        jdbc.query(
            FIND_BY_CARD,
            MapSqlParameterSource()
                .addValue("cardToken", cardToken)
                .addValue("before", before?.let(Timestamp::from))
                .addValue("limit", limit),
            ROW_MAPPER,
        )

    fun findByAuthId(authId: String): CardTransaction? =
        jdbc.query(FIND_BY_AUTH_ID, MapSqlParameterSource("authId", authId), ROW_MAPPER).firstOrNull()

    private fun CardTransaction.toParams() = MapSqlParameterSource()
        .addValue("authId", authId)
        .addValue("cardToken", cardToken)
        .addValue("merchantId", merchantId)
        .addValue("amount", amount)
        .addValue("currency", currency)
        .addValue("merchantCountry", merchantCountry)
        .addValue("channel", channel)
        .addValue("status", status.name)
        .addValue("authorisedAt", Timestamp.from(authorisedAt))
        .addValue("sourcePartition", sourcePartition)
        .addValue("sourceOffset", sourceOffset)

    companion object {
        private val UPSERT = """
            INSERT INTO card_transaction (auth_id, card_token, merchant_id, amount, currency,
                                          merchant_country, channel, status, authorised_at,
                                          source_partition, source_offset)
            VALUES (:authId, :cardToken, :merchantId, :amount, :currency,
                    :merchantCountry, :channel, :status, :authorisedAt,
                    :sourcePartition, :sourceOffset)
            ON CONFLICT (auth_id) DO NOTHING
        """.trimIndent()

        private val FIND_BY_CARD = """
            SELECT auth_id, card_token, merchant_id, amount, currency, merchant_country,
                   channel, status, authorised_at, source_partition, source_offset
              FROM card_transaction
             WHERE card_token = :cardToken
               AND (CAST(:before AS timestamptz) IS NULL OR authorised_at < CAST(:before AS timestamptz))
             ORDER BY authorised_at DESC
             LIMIT :limit
        """.trimIndent()

        private val FIND_BY_AUTH_ID = """
            SELECT auth_id, card_token, merchant_id, amount, currency, merchant_country,
                   channel, status, authorised_at, source_partition, source_offset
              FROM card_transaction
             WHERE auth_id = :authId
        """.trimIndent()

        private val ROW_MAPPER = RowMapper { rs, _ ->
            CardTransaction(
                authId = rs.getString("auth_id"),
                cardToken = rs.getString("card_token"),
                merchantId = rs.getString("merchant_id"),
                amount = rs.getBigDecimal("amount"),
                currency = rs.getString("currency"),
                merchantCountry = rs.getString("merchant_country") ?: "",
                channel = rs.getString("channel") ?: "",
                status = TransactionStatus.valueOf(rs.getString("status")),
                authorisedAt = rs.getTimestamp("authorised_at").toInstant(),
                sourcePartition = rs.getInt("source_partition"),
                sourceOffset = rs.getLong("source_offset"),
            )
        }
    }
}
