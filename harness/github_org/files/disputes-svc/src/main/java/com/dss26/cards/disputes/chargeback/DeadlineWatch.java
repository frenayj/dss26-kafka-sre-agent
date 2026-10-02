package com.dss26.cards.disputes.chargeback;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;
import java.util.concurrent.atomic.AtomicInteger;

/** Exposes how many open cases are inside the representment warning window. */
@Component
public class DeadlineWatch {

    private final ChargebackRepository repository;
    private final Clock clock;
    private final AtomicInteger dueSoon;

    public DeadlineWatch(ChargebackRepository repository, Clock clock, MeterRegistry meters) {
        this.repository = repository;
        this.clock = clock;
        this.dueSoon = meters.gauge("disputes.chargebacks.due_soon", new AtomicInteger());
    }

    @Scheduled(cron = "0 */15 * * * *", zone = "Europe/Paris")
    public void refresh() {
        int count = 0;
        for (String id : repository.openIds()) {
            Chargeback cb = repository.find(id).orElse(null);
            if (cb != null && RepresentmentDeadlines.dueSoon(cb.network(), cb.openedAt(), clock.instant())) {
                count++;
            }
        }
        dueSoon.set(count);
    }
}
