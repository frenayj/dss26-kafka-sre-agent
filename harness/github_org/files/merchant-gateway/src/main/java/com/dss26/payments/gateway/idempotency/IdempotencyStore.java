package com.dss26.payments.gateway.idempotency;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import com.dss26.payments.gateway.GatewayProperties;
import com.dss26.payments.gateway.api.AuthorisationRejectedException;

/**
 * Remembers which auth id was issued for an Idempotency-Key, so an acquirer
 * retrying after a timeout does not publish the same authorisation twice.
 * In memory per pod; merchants are pinned to pods by the load balancer.
 */
@Component
public class IdempotencyStore {

    private static final int SWEEP_EVERY = 10_000;

    private final Map<String, Entry> entries = new ConcurrentHashMap<>();
    private final Duration ttl;
    private final Clock clock;
    private int reservations;

    @Autowired
    public IdempotencyStore(GatewayProperties properties, Clock clock) {
        this(properties.idempotencyTtl(), clock);
    }

    public IdempotencyStore(Duration ttl, Clock clock) {
        this.ttl = ttl;
        this.clock = clock;
    }

    /**
     * Reserves {@code key} for {@code authId}. If the key was already used for an
     * equal request within the TTL, returns the auth id issued then and reserves
     * nothing.
     *
     * @throws AuthorisationRejectedException 409 if the key was used for a different request
     */
    public Optional<String> reserve(String key, Object request, String authId) {
        Instant now = clock.instant();
        sweepOccasionally(now);
        Entry winner = entries.compute(key, (k, existing) ->
                existing == null || existing.expiresAt().isBefore(now)
                        ? new Entry(request, authId, now.plus(ttl))
                        : existing);
        if (winner.authId().equals(authId)) {
            return Optional.empty();
        }
        if (!winner.request().equals(request)) {
            throw AuthorisationRejectedException.idempotencyConflict(key);
        }
        return Optional.of(winner.authId());
    }

    private synchronized void sweepOccasionally(Instant now) {
        if (++reservations % SWEEP_EVERY == 0) {
            entries.values().removeIf(entry -> entry.expiresAt().isBefore(now));
        }
    }

    private record Entry(Object request, String authId, Instant expiresAt) {
    }
}
