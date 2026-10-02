package com.dss26.customer.profile.gdpr;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * GDPR article 17 erasure, after the retention periods that override it
 * (five years after the relationship ends for AML records, ten for
 * accounting). Personal fields are overwritten in place; the customer id
 * stays so ledger and audit references remain valid.
 */
@Service
public class ErasureService {

    private static final Logger log = LoggerFactory.getLogger(ErasureService.class);

    private final NamedParameterJdbcTemplate jdbc;

    public ErasureService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean erase(String customerId) {
        Boolean blocked = jdbc.queryForObject("""
                SELECT EXISTS (SELECT 1 FROM customer_account
                                WHERE customer_id = :id
                                  AND (closed_at IS NULL OR closed_at > now() - interval '5 years'))
                """, new MapSqlParameterSource("id", customerId), Boolean.class);
        if (Boolean.TRUE.equals(blocked)) {
            log.info("Erasure for {} deferred: retention period still running", customerId);
            return false;
        }
        jdbc.update("""
                UPDATE customer_profile
                   SET first_name = 'ERASED', last_name = 'ERASED', date_of_birth = NULL, nationality = NULL,
                       email = NULL, phone = NULL, address = NULL, erased_at = now()
                 WHERE customer_id = :id
                """, new MapSqlParameterSource("id", customerId));
        jdbc.update("DELETE FROM customer_consent WHERE customer_id = :id", new MapSqlParameterSource("id", customerId));
        return true;
    }
}
