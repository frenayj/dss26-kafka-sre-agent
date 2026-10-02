package com.dss26.kyc.onboarding.verification

import java.time.Instant
import java.time.LocalDate

enum class Method { DOCUMENT_PHOTO, VIDEO_CALL, BANK_ACCOUNT_VERIFICATION, ELECTRONIC_ID, IN_BRANCH }
enum class Outcome { PASS, FAIL, MANUAL_REVIEW, EXPIRED }
enum class RiskRating { LOW, MEDIUM, HIGH }

data class Applicant(
    val customerId: String,
    val firstName: String,
    val lastName: String,
    val dateOfBirth: LocalDate,
    val nationality: String,
    val countryOfResidence: String,
    val idvSessionId: String,
    val method: Method,
    val pep: Boolean = false,
)

data class VerificationResult(
    val kycReference: String,
    val customerId: String,
    val method: Method,
    val outcome: Outcome,
    val riskRating: RiskRating,
    val verifiedAt: Instant,
    val expiresAt: Instant,
)
