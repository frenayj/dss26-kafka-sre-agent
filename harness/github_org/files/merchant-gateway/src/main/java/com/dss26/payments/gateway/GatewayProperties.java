package com.dss26.payments.gateway;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * The {@code gateway.*} block of application.yml.
 */
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        String topic,
        Duration sendTimeout,
        Duration idempotencyTtl,
        String tier,
        RateLimit rateLimit) {

    public record RateLimit(int perSecond, int burst) {
    }
}
