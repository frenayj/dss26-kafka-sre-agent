package com.dss26.cards.disputes.chargeback;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

/**
 * Days we have to respond to a chargeback before the network rules it in the
 * cardholder's favour: 30 for a Visa dispute response, 45 for a Mastercard
 * second presentment. Cases inside the warning window go to the top of the
 * analysts' queue.
 */
public final class RepresentmentDeadlines {

    static final Duration WARNING_WINDOW = Duration.ofDays(5);

    private RepresentmentDeadlines() {
    }

    public static LocalDate deadline(CardNetwork network, Instant openedAt) {
        LocalDate opened = openedAt.atZone(ZoneOffset.UTC).toLocalDate();
        return switch (network) {
            case VISA -> opened.plusDays(30);
            case MASTERCARD -> opened.plusDays(45);
        };
    }

    public static boolean dueSoon(CardNetwork network, Instant openedAt, Instant now) {
        Instant due = deadline(network, openedAt).atStartOfDay(ZoneOffset.UTC).toInstant();
        return !now.isAfter(due) && Duration.between(now, due).compareTo(WARNING_WINDOW) <= 0;
    }
}
