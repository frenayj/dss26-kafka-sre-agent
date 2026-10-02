package com.dss26.cards.lifecycle.card

import com.dss26.cards.events.BlockReason
import com.dss26.cards.events.CardFormFactor
import org.springframework.jdbc.core.simple.JdbcClient
import org.springframework.stereotype.Repository
import java.sql.Timestamp

@Repository
class CardRepository(private val jdbc: JdbcClient) {

    fun insert(card: Card) {
        jdbc.sql(
            """
            INSERT INTO card (card_token, customer_id, product_code, form_factor, bin, expiry_yyyymm, state, updated_at)
            VALUES (:token, :customer, :product, :formFactor, :bin, :expiry, :state, :updatedAt)
            """.trimIndent(),
        )
            .param("token", card.cardToken)
            .param("customer", card.customerId)
            .param("product", card.productCode)
            .param("formFactor", card.formFactor.name)
            .param("bin", card.bin)
            .param("expiry", card.expiryYyyymm)
            .param("state", card.state.name)
            .param("updatedAt", Timestamp.from(card.updatedAt))
            .update()
    }

    fun updateState(card: Card) {
        jdbc.sql("UPDATE card SET state = :state, block_reason = :reason, updated_at = :updatedAt WHERE card_token = :token")
            .param("token", card.cardToken)
            .param("state", card.state.name)
            .param("reason", card.blockReason?.name)
            .param("updatedAt", Timestamp.from(card.updatedAt))
            .update()
    }

    fun find(cardToken: String): Card? = select("SELECT * FROM card WHERE card_token = :token", cardToken)

    fun findForUpdate(cardToken: String): Card? =
        select("SELECT * FROM card WHERE card_token = :token FOR UPDATE", cardToken)

    private fun select(sql: String, cardToken: String): Card? =
        jdbc.sql(sql)
            .param("token", cardToken)
            .query { rs, _ ->
                Card(
                    cardToken = rs.getString("card_token"),
                    customerId = rs.getString("customer_id"),
                    productCode = rs.getString("product_code"),
                    formFactor = CardFormFactor.valueOf(rs.getString("form_factor")),
                    bin = rs.getString("bin"),
                    expiryYyyymm = rs.getString("expiry_yyyymm"),
                    state = CardState.valueOf(rs.getString("state")),
                    blockReason = rs.getString("block_reason")?.let(BlockReason::valueOf),
                    updatedAt = rs.getTimestamp("updated_at").toInstant(),
                )
            }
            .optional()
            .orElse(null)
}
