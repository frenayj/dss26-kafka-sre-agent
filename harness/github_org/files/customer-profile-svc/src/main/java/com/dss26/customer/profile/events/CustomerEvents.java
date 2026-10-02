package com.dss26.customer.profile.events;

import com.dss26.customer.events.AccountOpened;
import com.dss26.customer.events.ChangedBy;
import com.dss26.customer.events.ConsentGranted;
import com.dss26.customer.events.ConsentType;
import com.dss26.customer.events.ProfileUpdated;
import org.apache.avro.specific.SpecificRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.List;

/** customer.* events, keyed by customer id, sent after the surrounding transaction commits. */
@Component
public class CustomerEvents {

    static final String ACCOUNT_OPENED = "customer.account.opened.v1";
    static final String PROFILE_UPDATED = "customer.profile.updated.v1";
    static final String CONSENT_GRANTED = "customer.consent.granted.v1";

    private final KafkaTemplate<String, SpecificRecord> kafka;
    private final Clock clock;

    public CustomerEvents(KafkaTemplate<String, SpecificRecord> kafka) {
        this.kafka = kafka;
        this.clock = Clock.systemUTC();
    }

    public void profileUpdated(String customerId, List<String> changedFields, String changedBy, String agentId) {
        afterCommit(PROFILE_UPDATED, customerId, ProfileUpdated.newBuilder()
                .setCustomerId(customerId)
                .setChangedFields(changedFields)
                .setChangedBy(ChangedBy.valueOf(changedBy))
                .setAgentId(agentId)
                .setChangedAt(clock.instant())
                .build());
    }

    public void consentGranted(String customerId, String consentId, ConsentType type, String scope, Instant expiresAt) {
        afterCommit(CONSENT_GRANTED, customerId, ConsentGranted.newBuilder()
                .setCustomerId(customerId)
                .setConsentId(consentId)
                .setConsentType(type)
                .setScope(scope)
                .setExpiresAt(expiresAt)
                .setGrantedAt(clock.instant())
                .build());
    }

    public void accountOpened(String customerId, String accountNumber, String productCode, String kycReference,
                              String currency) {
        afterCommit(ACCOUNT_OPENED, customerId, AccountOpened.newBuilder()
                .setCustomerId(customerId)
                .setAccountNumber(accountNumber)
                .setProductCode(productCode)
                .setKycReference(kycReference)
                .setOpeningBalance(BigDecimal.ZERO.doubleValue())
                .setCurrency(currency)
                .setOpenedAt(clock.instant())
                .build());
    }

    private void afterCommit(String topic, String key, SpecificRecord value) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            kafka.send(topic, key, value);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                kafka.send(topic, key, value);
            }
        });
    }
}
