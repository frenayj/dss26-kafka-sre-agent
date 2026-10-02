package com.dss26.cards.disputes.chargeback;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;

class RepresentmentDeadlinesTest {

    private static final Instant OPENED = Instant.parse("2025-09-01T10:00:00Z");

    @Test
    void visaGivesThirtyDays() {
        assertThat(RepresentmentDeadlines.deadline(CardNetwork.VISA, OPENED)).isEqualTo(LocalDate.of(2025, 10, 1));
    }

    @Test
    void mastercardGivesFortyFiveDays() {
        assertThat(RepresentmentDeadlines.deadline(CardNetwork.MASTERCARD, OPENED)).isEqualTo(LocalDate.of(2025, 10, 16));
    }

    @Test
    void flagsCasesInsideTheWarningWindow() {
        assertThat(RepresentmentDeadlines.dueSoon(CardNetwork.VISA, OPENED, Instant.parse("2025-09-27T09:00:00Z"))).isTrue();
        assertThat(RepresentmentDeadlines.dueSoon(CardNetwork.VISA, OPENED, Instant.parse("2025-09-20T09:00:00Z"))).isFalse();
        assertThat(RepresentmentDeadlines.dueSoon(CardNetwork.VISA, OPENED, Instant.parse("2025-10-02T09:00:00Z"))).isFalse();
    }
}
