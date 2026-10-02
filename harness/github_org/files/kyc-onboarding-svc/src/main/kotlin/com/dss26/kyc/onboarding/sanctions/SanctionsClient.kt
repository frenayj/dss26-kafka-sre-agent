package com.dss26.kyc.onboarding.sanctions

import org.springframework.beans.factory.annotation.Value
import org.springframework.boot.web.client.RestTemplateBuilder
import org.springframework.stereotype.Component
import java.time.Duration

data class ScreeningRequest(val customerId: String, val name: String, val trigger: String)
data class ScreeningResponse(val screeningId: String, val outcome: String, val matchScore: Double)

/** sanctions-screening-svc, POST /v1/screenings. */
@Component
class SanctionsClient(builder: RestTemplateBuilder, @Value("\${kyc.sanctions.base-url}") baseUrl: String) {
    private val rest = builder
        .rootUri(baseUrl)
        .setConnectTimeout(Duration.ofSeconds(1))
        .setReadTimeout(Duration.ofSeconds(3))
        .build()

    fun screenAtAccountOpen(customerId: String, fullName: String): ScreeningResponse =
        rest.postForObject("/v1/screenings", ScreeningRequest(customerId, fullName, "ACCOUNT_OPEN"),
            ScreeningResponse::class.java) ?: error("empty sanctions response for $customerId")
}
