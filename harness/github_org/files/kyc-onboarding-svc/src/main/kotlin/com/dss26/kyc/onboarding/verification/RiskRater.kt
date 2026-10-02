package com.dss26.kyc.onboarding.verification

/**
 * Customer risk rating at onboarding. Factors and weights come from the
 * bank's business-wide risk assessment (CMP owner: claire.martin); change them
 * only with Compliance sign-off.
 */
object RiskRater {

    /** EU list of high-risk third countries plus the FATF increased-monitoring list, as ISO-3166 alpha-2. */
    val HIGH_RISK_COUNTRIES = setOf("AF", "BF", "CM", "CD", "HT", "IR", "KP", "ML", "MM", "MZ", "NG", "SS", "SY", "VE", "YE")

    fun rate(applicant: Applicant, sanctionsPotentialMatch: Boolean): RiskRating {
        var score = 0
        if (applicant.pep) score += 3
        if (applicant.nationality in HIGH_RISK_COUNTRIES) score += 2
        if (applicant.countryOfResidence in HIGH_RISK_COUNTRIES) score += 2
        if (applicant.countryOfResidence !in EEA) score += 1
        if (sanctionsPotentialMatch) score += 3
        // Strong, regulated identification lowers the residual risk slightly.
        if (applicant.method == Method.ELECTRONIC_ID || applicant.method == Method.IN_BRANCH) score -= 1
        return when {
            score >= 3 -> RiskRating.HIGH
            score >= 1 -> RiskRating.MEDIUM
            else -> RiskRating.LOW
        }
    }

    private val EEA = setOf(
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT",
        "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO",
    )
}
