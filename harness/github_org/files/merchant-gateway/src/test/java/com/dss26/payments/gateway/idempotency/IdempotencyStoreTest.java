package com.dss26.payments.gateway.idempotency;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import com.dss26.payments.gateway.api.AuthorisationRejectedException;

class IdempotencyStoreTest {

    private final MutableClock clock = new MutableClock(Instant.parse("2023-11-06T10:00:00Z"));
    private final IdempotencyStore store = new IdempotencyStore(Duration.ofHours(24), clock);

    @Test
    void firstUseReservesTheKey() {
        assertThat(store.reserve("key-1", "request-a", "auth-1")).isEmpty();
    }

    @Test
    void replayOfTheSameRequestReturnsTheFirstAuthId() {
        store.reserve("key-1", "request-a", "auth-1");

        assertThat(store.reserve("key-1", "request-a", "auth-2")).contains("auth-1");
    }

    @Test
    void sameKeyWithADifferentRequestIsAConflict() {
        store.reserve("key-1", "request-a", "auth-1");

        assertThatThrownBy(() -> store.reserve("key-1", "request-b", "auth-2"))
                .isInstanceOf(AuthorisationRejectedException.class)
                .hasMessageContaining("key-1");
    }

    @Test
    void keysExpireAfterTheTtl() {
        store.reserve("key-1", "request-a", "auth-1");
        clock.advance(Duration.ofHours(25));

        assertThat(store.reserve("key-1", "request-b", "auth-2")).isEmpty();
    }

    private static final class MutableClock extends Clock {

        private Instant now;

        private MutableClock(Instant now) {
            this.now = now;
        }

        void advance(Duration by) {
            now = now.plus(by);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return now;
        }
    }
}
