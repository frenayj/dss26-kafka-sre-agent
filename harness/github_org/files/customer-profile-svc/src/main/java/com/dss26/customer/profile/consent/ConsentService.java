package com.dss26.customer.profile.consent;

import com.dss26.customer.events.ConsentType;
import com.dss26.customer.profile.events.CustomerEvents;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

/**
 * Consents the customer gives: PSD2 access for third-party providers,
 * marketing channels, data sharing. Every grant is evidence for PSD2 and GDPR
 * audits, so it is stored and published, never updated in place.
 */
@Service
public class ConsentService {

    /** PSD2 RTS (as amended in 2023): account information access needs SCA again every 180 days. */
    static final Duration AISP_VALIDITY = Duration.ofDays(180);

    private final NamedParameterJdbcTemplate jdbc;
    private final CustomerEvents events;
    private final Clock clock = Clock.systemUTC();

    public ConsentService(NamedParameterJdbcTemplate jdbc, CustomerEvents events) {
        this.jdbc = jdbc;
        this.events = events;
    }

    @Transactional
    public String grant(String customerId, ConsentType type, String scope) {
        String consentId = UUID.randomUUID().toString();
        Instant expiresAt = type == ConsentType.PSD2_AISP ? clock.instant().plus(AISP_VALIDITY) : null;
        jdbc.update("""
                INSERT INTO customer_consent (consent_id, customer_id, consent_type, scope, granted_at, expires_at)
                VALUES (:id, :customer, :type, :scope, now(), :expiresAt)
                """, new MapSqlParameterSource()
                .addValue("id", consentId)
                .addValue("customer", customerId)
                .addValue("type", type.name())
                .addValue("scope", scope)
                .addValue("expiresAt", expiresAt == null ? null : Timestamp.from(expiresAt)));
        events.consentGranted(customerId, consentId, type, scope, expiresAt);
        return consentId;
    }
}
