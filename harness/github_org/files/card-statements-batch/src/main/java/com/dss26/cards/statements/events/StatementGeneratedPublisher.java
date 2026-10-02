package com.dss26.cards.statements.events;

import com.dss26.cards.events.StatementGenerated;
import com.dss26.cards.statements.job.Model.CardStatement;
import org.apache.avro.specific.SpecificRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.concurrent.TimeUnit;

/**
 * cards.statement.generated.v1, keyed by customer: notifications sends the
 * "your statement is ready" push, the apps list it under Statements.
 */
@Component
public class StatementGeneratedPublisher {

    static final String TOPIC = "cards.statement.generated.v1";
    private final KafkaTemplate<String, SpecificRecord> kafka;

    public StatementGeneratedPublisher(KafkaTemplate<String, SpecificRecord> kafka) {
        this.kafka = kafka;
    }

    public void generated(CardStatement statement) {
        StatementGenerated event = StatementGenerated.newBuilder()
                .setStatementId(statement.statementId())
                .setCustomerId(statement.cycle().customerId())
                .setCardToken(statement.cycle().cardToken())
                .setStatementPeriod(statement.cycle().period())
                .setClosingBalance(statement.closingBalance().doubleValue())
                .setCurrency(statement.cycle().currency())
                .setTransactionCount(statement.lines().size())
                .setGeneratedAt(Instant.now())
                .build();
        try {
            // Synchronous on purpose: the chunk only commits once the event is acknowledged.
            kafka.send(TOPIC, statement.cycle().customerId(), event).get(10, TimeUnit.SECONDS);
        } catch (Exception e) {
            throw new IllegalStateException("Could not publish statement " + statement.statementId(), e);
        }
    }
}
