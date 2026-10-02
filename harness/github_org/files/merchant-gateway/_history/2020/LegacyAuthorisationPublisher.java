package com.dss26.payments.gateway.events;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import com.dss26.payments.gateway.api.AuthorisationRequest;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Publishes accepted authorisations as JSON to the topic fraud-scoring reads.
 */
@Component
public class LegacyAuthorisationPublisher {

    private final KafkaTemplate<String, String> kafka;
    private final ObjectMapper json;
    private final String topic;

    public LegacyAuthorisationPublisher(KafkaTemplate<String, String> kafka, ObjectMapper json,
            @Value("${gateway.topic}") String topic) {
        this.kafka = kafka;
        this.json = json;
        this.topic = topic;
    }

    public void publish(String authId, AuthorisationRequest request, Instant receivedAt) {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("authId", authId);
        message.put("cardToken", request.getCardToken());
        message.put("merchantId", request.getMerchantId());
        message.put("amount", request.getAmount());
        message.put("currency", request.getCurrency());
        message.put("merchantCountry", request.getMerchantCountry());
        message.put("receivedAt", receivedAt.toString());
        try {
            kafka.send(topic, request.getCardToken(), json.writeValueAsString(message)).get(2, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted publishing authorisation " + authId, e);
        } catch (JsonProcessingException | ExecutionException | TimeoutException e) {
            throw new IllegalStateException("Could not publish authorisation " + authId, e);
        }
    }
}
