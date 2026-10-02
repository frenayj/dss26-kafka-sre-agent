package com.dss26.cards.clearing.matching;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * Read-only view of the issuer authorisation log (replicated from the core
 * authorisation host into the clearing database). Candidates are approved
 * authorisations on the same card and merchant in the last 30 days that have
 * not been matched yet.
 */
@Repository
public class AuthorisationLog {

    private static final String CANDIDATES = """
            SELECT auth_id, card_token, merchant_id, amount, currency
              FROM issuer_auth_log
             WHERE card_token = :card AND merchant_id = :merchant
               AND approved AND authorised_at > now() - interval '30 days'
               AND auth_id NOT IN (SELECT auth_id FROM clearing_match)
             ORDER BY authorised_at DESC
             LIMIT 20
            """;

    private final NamedParameterJdbcTemplate jdbc;

    public AuthorisationLog(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<MatchScorer.Authorisation> candidates(String cardToken, String merchantId) {
        return jdbc.query(CANDIDATES,
                new MapSqlParameterSource("card", cardToken).addValue("merchant", merchantId),
                (rs, n) -> new MatchScorer.Authorisation(rs.getString("auth_id"), rs.getString("card_token"),
                        rs.getString("merchant_id"), rs.getBigDecimal("amount"), rs.getString("currency")));
    }
}
