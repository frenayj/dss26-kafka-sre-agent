package com.dss26.payments.gateway.policy;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import com.dss26.payments.gateway.GatewayProperties;

/**
 * Token bucket per merchant_id, so one merchant's retry storm cannot starve the
 * others. Per pod: the load balancer pins a merchant to a pod.
 */
@Component
public class MerchantRateLimiter {

    private final Map<String, Bucket> buckets = new ConcurrentHashMap<>();
    private final double perSecond;
    private final double burst;
    private final LongSupplier nanoTime;

    @Autowired
    public MerchantRateLimiter(GatewayProperties properties) {
        this(properties.rateLimit().perSecond(), properties.rateLimit().burst(), System::nanoTime);
    }

    public MerchantRateLimiter(int perSecond, int burst, LongSupplier nanoTime) {
        this.perSecond = perSecond;
        this.burst = burst;
        this.nanoTime = nanoTime;
    }

    public boolean tryAcquire(String merchantId) {
        return buckets.computeIfAbsent(merchantId, id -> new Bucket(burst, nanoTime.getAsLong())).tryTake();
    }

    private final class Bucket {

        private double tokens;
        private long refilledAt;

        private Bucket(double tokens, long now) {
            this.tokens = tokens;
            this.refilledAt = now;
        }

        synchronized boolean tryTake() {
            long now = nanoTime.getAsLong();
            tokens = Math.min(burst, tokens + (now - refilledAt) / 1_000_000_000.0 * perSecond);
            refilledAt = now;
            if (tokens < 1) {
                return false;
            }
            tokens -= 1;
            return true;
        }
    }
}
