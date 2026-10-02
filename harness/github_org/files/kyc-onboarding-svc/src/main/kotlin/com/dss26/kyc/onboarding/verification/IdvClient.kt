package com.dss26.kyc.onboarding.verification

import org.springframework.beans.factory.annotation.Value
import org.springframework.boot.web.client.RestTemplateBuilder
import org.springframework.stereotype.Component
import java.time.Duration

/** Result of the identity verification session run by the IDV provider in the app. */
data class IdvReport(val sessionId: String, val documentAuthentic: Boolean, val faceMatch: Boolean, val livenessPassed: Boolean)

@Component
class IdvClient(
    builder: RestTemplateBuilder,
    @Value("\${kyc.idv.base-url}") baseUrl: String,
    @Value("\${kyc.idv.api-key}") apiKey: String,
) {
    private val rest = builder
        .rootUri(baseUrl)
        .defaultHeader("Authorization", "Token token=$apiKey")
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(10))
        .build()

    fun report(sessionId: String): IdvReport =
        rest.getForObject("/v3/sessions/{id}/report", IdvReport::class.java, sessionId)
            ?: error("IDV provider returned no report for $sessionId")
}
