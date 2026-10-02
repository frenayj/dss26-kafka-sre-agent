package com.dss26.kyc.onboarding.refresh

import org.slf4j.LoggerFactory
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.sql.Timestamp
import java.time.Clock
import java.time.Duration

/**
 * Every night, open a refresh task for verifications expiring in the next 30
 * days. The customer gets an in-app request; if it is not completed by expiry
 * the account is restricted by customer-profile-svc.
 */
@Component
class PeriodicRefreshJob(private val jdbc: NamedParameterJdbcTemplate, private val clock: Clock = Clock.systemUTC()) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(cron = "0 30 2 * * *", zone = "Europe/Paris")
    fun openRefreshTasks() {
        val horizon = clock.instant().plus(Duration.ofDays(30))
        val opened = jdbc.update(
            """
            INSERT INTO kyc_refresh_task (kyc_reference, customer_id, due_at, status)
            SELECT v.kyc_reference, v.customer_id, v.expires_at, 'OPEN'
              FROM kyc_verification v
             WHERE v.outcome = 'PASS' AND v.expires_at <= :horizon
               AND NOT EXISTS (SELECT 1 FROM kyc_refresh_task t WHERE t.kyc_reference = v.kyc_reference)
            """.trimIndent(),
            MapSqlParameterSource("horizon", Timestamp.from(horizon)),
        )
        log.info("Opened {} KYC refresh tasks due before {}", opened, horizon)
    }
}
