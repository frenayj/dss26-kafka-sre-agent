package com.dss26.cards.disputes.chargeback;

import com.dss26.cards.events.ChargebackCategory;
import com.dss26.cards.events.ChargebackOutcome;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Repository
public class ChargebackRepository {

    private final JdbcClient jdbc;

    public ChargebackRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(Chargeback cb) {
        jdbc.sql("""
                INSERT INTO chargeback (id, auth_id, merchant_id, network, disputed_amount, currency,
                                        reason_code, category, opened_at)
                VALUES (:id, :authId, :merchantId, :network, :amount, :currency, :reasonCode, :category, :openedAt)
                """)
                .param("id", cb.id())
                .param("authId", cb.authId())
                .param("merchantId", cb.merchantId())
                .param("network", cb.network().name())
                .param("amount", cb.disputedAmount())
                .param("currency", cb.currency())
                .param("reasonCode", cb.reasonCode())
                .param("category", cb.category().name())
                .param("openedAt", Timestamp.from(cb.openedAt()))
                .update();
    }

    public void resolve(String id, ChargebackOutcome outcome, BigDecimal recovered, Instant resolvedAt) {
        jdbc.sql("""
                UPDATE chargeback SET outcome = :outcome, recovered_amount = :recovered, resolved_at = :resolvedAt
                 WHERE id = :id AND outcome IS NULL
                """)
                .param("id", id)
                .param("outcome", outcome.name())
                .param("recovered", recovered)
                .param("resolvedAt", Timestamp.from(resolvedAt))
                .update();
    }

    public Optional<Chargeback> find(String id) {
        return jdbc.sql("SELECT * FROM chargeback WHERE id = :id")
                .param("id", id)
                .query((rs, n) -> new Chargeback(
                        rs.getString("id"),
                        rs.getString("auth_id"),
                        rs.getString("merchant_id"),
                        CardNetwork.valueOf(rs.getString("network")),
                        rs.getBigDecimal("disputed_amount"),
                        rs.getString("currency"),
                        rs.getString("reason_code"),
                        ChargebackCategory.valueOf(rs.getString("category")),
                        rs.getTimestamp("opened_at").toInstant(),
                        rs.getString("outcome") == null ? null : ChargebackOutcome.valueOf(rs.getString("outcome")),
                        rs.getBigDecimal("recovered_amount"),
                        rs.getTimestamp("resolved_at") == null ? null : rs.getTimestamp("resolved_at").toInstant()))
                .optional();
    }

    public List<String> openIds() {
        return jdbc.sql("SELECT id FROM chargeback WHERE outcome IS NULL ORDER BY opened_at")
                .query(String.class)
                .list();
    }
}
