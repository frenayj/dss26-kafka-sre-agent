package com.dss26.cards.disputes.chargeback;

import com.dss26.cards.events.ChargebackCategory;
import com.dss26.cards.events.ChargebackOutcome;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.NoSuchElementException;
import java.util.UUID;

@Service
public class ChargebackService {

    public record Opened(Chargeback chargeback) {
    }

    public record Resolved(Chargeback chargeback) {
    }

    private final ChargebackRepository repository;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public ChargebackService(ChargebackRepository repository, ApplicationEventPublisher events, Clock clock) {
        this.repository = repository;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public Chargeback open(String authId, String merchantId, CardNetwork network, BigDecimal amount,
                           String currency, String reasonCode) {
        ChargebackCategory category = ReasonCodes.categorise(network, reasonCode);
        Chargeback cb = new Chargeback(UUID.randomUUID().toString(), authId, merchantId, network, amount,
                currency, reasonCode, category, clock.instant(), null, null, null);
        repository.insert(cb);
        events.publishEvent(new Opened(cb));
        return cb;
    }

    @Transactional
    public Chargeback resolve(String id, ChargebackOutcome outcome, BigDecimal recovered) {
        Chargeback cb = repository.find(id).orElseThrow(() -> new NoSuchElementException(id));
        if (!cb.isOpen()) {
            return cb;
        }
        Instant now = clock.instant();
        repository.resolve(id, outcome, recovered, now);
        Chargeback resolved = repository.find(id).orElseThrow();
        events.publishEvent(new Resolved(resolved));
        return resolved;
    }
}
