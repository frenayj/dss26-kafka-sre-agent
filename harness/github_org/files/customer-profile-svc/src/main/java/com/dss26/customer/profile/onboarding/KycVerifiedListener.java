package com.dss26.customer.profile.onboarding;

import com.dss26.customer.profile.events.CustomerEvents;
import com.dss26.kyc.events.KycOutcome;
import com.dss26.kyc.events.KycVerificationCompleted;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

/**
 * Opens the current account once KYC passes. The account number is allocated
 * by the core ledger through core-banking-adapter; the customer record already
 * exists from the application step.
 */
@Component
public class KycVerifiedListener {

    private static final Logger log = LoggerFactory.getLogger(KycVerifiedListener.class);

    private final NamedParameterJdbcTemplate jdbc;
    private final CustomerEvents events;
    private final RestTemplate core;

    public KycVerifiedListener(NamedParameterJdbcTemplate jdbc, CustomerEvents events, RestTemplateBuilder builder,
                               @Value("${customer.core-banking-url}") String coreBankingUrl) {
        this.jdbc = jdbc;
        this.events = events;
        this.core = builder.rootUri(coreBankingUrl).build();
    }

    @Transactional
    @KafkaListener(id = "kyc-verified", topics = "kyc.verification.completed.v1", groupId = "customer-profile-svc")
    public void onVerification(KycVerificationCompleted kyc) {
        if (kyc.getOutcome() != KycOutcome.PASS) {
            return;
        }
        Integer existing = jdbc.queryForObject(
                "SELECT count(*) FROM customer_account WHERE kyc_reference = :ref",
                new MapSqlParameterSource("ref", kyc.getKycReference()), Integer.class);
        if (existing != null && existing > 0) {
            log.info("Account for {} already opened, skipping redelivery", kyc.getKycReference());
            return;
        }
        @SuppressWarnings("unchecked")
        Map<String, String> opened = core.postForObject("/v1/accounts",
                Map.of("customerId", kyc.getCustomerId(), "productCode", "CURRENT_EUR"), Map.class);
        String accountNumber = opened.get("accountNumber");
        jdbc.update("""
                INSERT INTO customer_account (account_number, customer_id, product_code, kyc_reference, currency)
                VALUES (:account, :customer, 'CURRENT_EUR', :ref, 'EUR')
                """, new MapSqlParameterSource()
                .addValue("account", accountNumber)
                .addValue("customer", kyc.getCustomerId())
                .addValue("ref", kyc.getKycReference()));
        events.accountOpened(kyc.getCustomerId(), accountNumber, "CURRENT_EUR", kyc.getKycReference(), "EUR");
    }
}
