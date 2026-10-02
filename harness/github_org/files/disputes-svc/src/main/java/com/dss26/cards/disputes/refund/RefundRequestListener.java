package com.dss26.cards.disputes.refund;

import com.dss26.cards.events.RefundCompleted;
import com.dss26.cards.events.RefundRequested;
import org.apache.avro.specific.SpecificRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Clock;

/**
 * Merchant refunds: credit the cardholder and close the refund lifecycle. The
 * settlement batch id is unknown at this point and arrives with the next
 * settlement cycle.
 */
@Component
public class RefundRequestListener {

    private static final Logger log = LoggerFactory.getLogger(RefundRequestListener.class);
    static final String COMPLETED_TOPIC = "cards.refund.completed.v1";

    private final JdbcClient jdbc;
    private final KafkaTemplate<String, SpecificRecord> kafka;
    private final Clock clock;

    public RefundRequestListener(JdbcClient jdbc, KafkaTemplate<String, SpecificRecord> kafka, Clock clock) {
        this.jdbc = jdbc;
        this.kafka = kafka;
        this.clock = clock;
    }

    @Transactional
    @KafkaListener(id = "refunds", topics = "cards.refund.requested.v1", groupId = "disputes-svc-refunds")
    public void onRefundRequested(RefundRequested request) {
        int inserted = jdbc.sql("""
                INSERT INTO refund (id, auth_id, card_token, merchant_id, amount, currency, reason, requested_at)
                VALUES (:id, :authId, :cardToken, :merchantId, :amount, :currency, :reason, :requestedAt)
                ON CONFLICT (id) DO NOTHING
                """)
                .param("id", request.getRefundId())
                .param("authId", request.getAuthId())
                .param("cardToken", request.getCardToken())
                .param("merchantId", request.getMerchantId())
                .param("amount", request.getAmount())
                .param("currency", request.getCurrency())
                .param("reason", request.getReasonCode().name())
                .param("requestedAt", Timestamp.from(request.getRequestedAt()))
                .update();
        if (inserted == 0) {
            log.info("Refund {} already processed, skipping", request.getRefundId());
            return;
        }
        kafka.send(COMPLETED_TOPIC, request.getRefundId(), RefundCompleted.newBuilder()
                .setRefundId(request.getRefundId())
                .setCompletedAmount(request.getAmount())
                .setCurrency(request.getCurrency())
                .setSettlementBatchId(null)
                .setCompletedAt(clock.instant())
                .build());
    }
}
