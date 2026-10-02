package com.dss26.kyc.onboarding.application

import com.dss26.kyc.onboarding.verification.Applicant
import com.dss26.kyc.onboarding.verification.VerificationService
import com.dss26.kyc.onboarding.verification.VerificationResult
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

/**
 * Called by the mobile and web onboarding journeys once the applicant has
 * completed the identity step with the IDV provider.
 */
@RestController
@RequestMapping("/v1/applications")
class OnboardingController(private val verification: VerificationService) {

    @PostMapping("/{applicationId}/verification")
    fun verify(@PathVariable applicationId: String, @RequestBody applicant: Applicant): VerificationResult =
        verification.verify(applicationId, applicant)
}
