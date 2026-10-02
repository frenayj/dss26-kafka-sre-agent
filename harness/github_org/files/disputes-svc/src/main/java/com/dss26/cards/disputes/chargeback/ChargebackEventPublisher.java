package com.dss26.cards.disputes.chargeback;

import com.dss26.cards.events.ChargebackOpened;
import com.dss26.cards.events.ChargebackResolved;
import org.apache.avro.specific.SpecificRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

import java.math.BigDecimal;
import java.time.Duration;

/**
 * Publishes after the database commit, keyed by chargeback id. The key is also
 * the Elasticsearch document id (sink-elastic-disputes-search runs with
 * key.ignore=false), so an update replaces the document instead of adding one.
 */
@Component
public class ChargebackEventPublisher {

    static final String OPENED_TOPIC = "cards.chargeback.opened.v1";
    static final String RESOLVED_TOPIC = "cards.chargeback.resolved.v1";

    private final KafkaTemplate<String, SpecificRecord> kafka;

    public ChargebackEventPublisher(KafkaTemplate<String, SpecificRecord> kafka) {
        this.kafka = kafka;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(ChargebackService.Opened event) {
        Chargeback cb = event.chargeback();
        kafka.send(OPENED_TOPIC, cb.id(), ChargebackOpened.newBuilder()
                .setChargebackId(cb.id())
                .setAuthId(cb.authId())
                .setMerchantId(cb.merchantId())
                .setDisputedAmount(cb.disputedAmount().doubleValue())
                .setCurrency(cb.currency())
                .setReasonCode(cb.reasonCode())
                .setReasonCategory(cb.category())
                .setOpenedAt(cb.openedAt())
                .build());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(ChargebackService.Resolved event) {
        Chargeback cb = event.chargeback();
        BigDecimal recovered = cb.recoveredAmount() == null ? BigDecimal.ZERO : cb.recoveredAmount();
        kafka.send(RESOLVED_TOPIC, cb.id(), ChargebackResolved.newBuilder()
                .setChargebackId(cb.id())
                .setOutcome(cb.outcome())
                .setRecoveredAmount(recovered.doubleValue())
                .setCurrency(cb.currency())
                .setResolutionDays((int) Duration.between(cb.openedAt(), cb.resolvedAt()).toDays())
                .setResolvedAt(cb.resolvedAt())
                .build());
    }
}
