package com.dss26.cards.statements.job;

import com.dss26.cards.statements.job.Model.StatementLine;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

import java.sql.Timestamp;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.List;

/**
 * Reads card_transaction from the txn-history-builder read replica. The
 * schema belongs to txn-history-builder; we only read it.
 */
@Component
public class JdbcStatementLines implements StatementLines {

    private static final ZoneId PARIS = ZoneId.of("Europe/Paris");
    private final NamedParameterJdbcTemplate jdbc;

    public JdbcStatementLines(@Qualifier("txnHistoryJdbc") NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public List<StatementLine> forCard(String cardToken, YearMonth period) {
        return jdbc.query("""
                SELECT auth_id, merchant_id, amount, status, authorised_at
                  FROM card_transaction
                 WHERE card_token = :card
                   AND authorised_at >= :from AND authorised_at < :to
                 ORDER BY authorised_at
                """,
                new MapSqlParameterSource("card", cardToken)
                        .addValue("from", Timestamp.from(period.atDay(1).atStartOfDay(PARIS).toInstant()))
                        .addValue("to", Timestamp.from(period.plusMonths(1).atDay(1).atStartOfDay(PARIS).toInstant())),
                (rs, n) -> new StatementLine(rs.getString("auth_id"), rs.getString("merchant_id"),
                        rs.getBigDecimal("amount"), rs.getString("status"), rs.getTimestamp("authorised_at").toInstant()));
    }
}
