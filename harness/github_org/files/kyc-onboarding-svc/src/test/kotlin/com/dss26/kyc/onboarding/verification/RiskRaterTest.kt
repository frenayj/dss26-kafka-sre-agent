package com.dss26.kyc.onboarding.verification

import org.junit.jupiter.api.Test
import java.time.LocalDate
import kotlin.test.assertEquals

class RiskRaterTest {

    private fun applicant(nationality: String = "FR", residence: String = "FR", pep: Boolean = false,
                          method: Method = Method.DOCUMENT_PHOTO) =
        Applicant("CUST-30418", "Camille", "Laurent", LocalDate.of(1988, 4, 12), nationality, residence,
            "idv-7f1c", method, pep)

    @Test
    fun `EEA resident with no risk factors is LOW`() {
        assertEquals(RiskRating.LOW, RiskRater.rate(applicant(), sanctionsPotentialMatch = false))
    }

    @Test
    fun `resident outside the EEA is MEDIUM`() {
        assertEquals(RiskRating.MEDIUM, RiskRater.rate(applicant(residence = "CH"), sanctionsPotentialMatch = false))
    }

    @Test
    fun `politically exposed person is HIGH`() {
        assertEquals(RiskRating.HIGH, RiskRater.rate(applicant(pep = true), sanctionsPotentialMatch = false))
    }

    @Test
    fun `potential sanctions match is HIGH until cleared`() {
        assertEquals(RiskRating.HIGH, RiskRater.rate(applicant(), sanctionsPotentialMatch = true))
    }

    @Test
    fun `electronic ID offsets a single medium factor`() {
        assertEquals(RiskRating.LOW,
            RiskRater.rate(applicant(residence = "CH", method = Method.ELECTRONIC_ID), sanctionsPotentialMatch = false))
    }

    @Test
    fun `review cycle follows the rating`() {
        assertEquals(365, VerificationService.refreshAfter(RiskRating.HIGH).toDays())
        assertEquals(5 * 365, VerificationService.refreshAfter(RiskRating.LOW).toDays())
    }
}
