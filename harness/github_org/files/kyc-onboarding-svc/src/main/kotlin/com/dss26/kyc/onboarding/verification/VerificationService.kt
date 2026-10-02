package com.dss26.kyc.onboarding.verification

import com.dss26.kyc.onboarding.events.KycEventPublisher
import com.dss26.kyc.onboarding.sanctions.SanctionsClient
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.sql.Timestamp
import java.time.Clock
import java.time.Duration
import java.util.UUID

@Service
class VerificationService(
    private val idv: IdvClient,
    private val sanctions: SanctionsClient,
    private val events: KycEventPublisher,
    private val jdbc: NamedParameterJdbcTemplate,
    private val clock: Clock = Clock.systemUTC(),
) {

    @Transactional
    fun verify(applicationId: String, applicant: Applicant): VerificationResult {
        val report = idv.report(applicant.idvSessionId)
        val screening = sanctions.screenAtAccountOpen(applicant.customerId, "${applicant.firstName} ${applicant.lastName}")
        val potentialMatch = screening.outcome == "POTENTIAL_MATCH"

        val outcome = when {
            !report.documentAuthentic || !report.livenessPassed -> Outcome.FAIL
            !report.faceMatch || potentialMatch -> Outcome.MANUAL_REVIEW
            else -> Outcome.PASS
        }
        val rating = RiskRater.rate(applicant, potentialMatch)
        val now = clock.instant()
        val result = VerificationResult(
            kycReference = "KYC-" + UUID.randomUUID().toString().take(13).uppercase(),
            customerId = applicant.customerId,
            method = applicant.method,
            outcome = outcome,
            riskRating = rating,
            verifiedAt = now,
            expiresAt = now.plus(refreshAfter(rating)),
        )
        jdbc.update(
            """
            INSERT INTO kyc_verification (kyc_reference, application_id, customer_id, method, outcome,
                                          risk_rating, sanctions_screening_id, verified_at, expires_at)
            VALUES (:ref, :app, :customer, :method, :outcome, :rating, :screening, :verifiedAt, :expiresAt)
            """.trimIndent(),
            MapSqlParameterSource()
                .addValue("ref", result.kycReference)
                .addValue("app", applicationId)
                .addValue("customer", result.customerId)
                .addValue("method", result.method.name)
                .addValue("outcome", result.outcome.name)
                .addValue("rating", result.riskRating.name)
                .addValue("screening", screening.screeningId)
                .addValue("verifiedAt", Timestamp.from(result.verifiedAt))
                .addValue("expiresAt", Timestamp.from(result.expiresAt)),
        )
        events.verificationCompleted(result)
        return result
    }

    companion object {
        /** Periodic review cycle by risk rating: 1 year HIGH, 3 years MEDIUM, 5 years LOW. */
        fun refreshAfter(rating: RiskRating): Duration = when (rating) {
            RiskRating.HIGH -> Duration.ofDays(365)
            RiskRating.MEDIUM -> Duration.ofDays(3 * 365)
            RiskRating.LOW -> Duration.ofDays(5 * 365)
        }
    }
}
