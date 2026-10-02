package com.dss26.payments.gateway.policy;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

class MerchantRateLimiterTest {

    private final AtomicLong nanos = new AtomicLong();
    private final MerchantRateLimiter limiter = new MerchantRateLimiter(10, 20, nanos::get);

    @Test
    void allowsABurstThenRefuses() {
        for (int i = 0; i < 20; i++) {
            assertThat(limiter.tryAcquire("mch_lumen_coffee")).as("request %d", i).isTrue();
        }
        assertThat(limiter.tryAcquire("mch_lumen_coffee")).isFalse();
    }

    @Test
    void refillsAtTheConfiguredRate() {
        for (int i = 0; i < 20; i++) {
            limiter.tryAcquire("mch_lumen_coffee");
        }
        nanos.addAndGet(500_000_000L);

        for (int i = 0; i < 5; i++) {
            assertThat(limiter.tryAcquire("mch_lumen_coffee")).isTrue();
        }
        assertThat(limiter.tryAcquire("mch_lumen_coffee")).isFalse();
    }

    @Test
    void merchantsHaveSeparateBuckets() {
        for (int i = 0; i < 20; i++) {
            limiter.tryAcquire("mch_lumen_coffee");
        }

        assertThat(limiter.tryAcquire("mch_lumen_coffee")).isFalse();
        assertThat(limiter.tryAcquire("mch_halcyon_retail")).isTrue();
    }
}
