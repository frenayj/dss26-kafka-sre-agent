package com.dss26.payments.hub.screening;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.util.Map;

/**
 * sanctions-screening-svc for cross-border payments. A payment with a
 * potential match is held for the sanctions team, never sent.
 */
@Component
public class SanctionsScreeningClient {

    private final RestTemplate rest;

    public SanctionsScreeningClient(RestTemplateBuilder builder, @Value("${hub.sanctions.base-url}") String baseUrl) {
        this.rest = builder.rootUri(baseUrl)
                .setConnectTimeout(Duration.ofSeconds(1))
                .setReadTimeout(Duration.ofSeconds(3))
                .build();
    }

    @SuppressWarnings("unchecked")
    public boolean isClear(String customerId, String creditorName) {
        Map<String, Object> resp = rest.postForObject("/v1/screenings",
                Map.of("customerId", customerId, "name", creditorName, "trigger", "CROSS_BORDER_TXN"), Map.class);
        return resp != null && "NO_HIT".equals(resp.get("outcome"));
    }
}
