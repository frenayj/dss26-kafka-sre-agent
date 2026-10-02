package com.dss26.payments.gateway.events;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.kafka.KafkaProperties;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import com.dss26.payments.gateway.api.AuthorisationRequest;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Keeps writing the old JSON message to acq.auth.requests while fraud-scoring
 * moves to cards.authorisation.requested.v1. Has its own String producer: the
 * default one now serialises Avro.
 */
@Component
public class LegacyAuthorisationPublisher {

    private final KafkaTemplate<String, String> kafka;
    private final ObjectMapper json;
    private final String topic;

    public LegacyAuthorisationPublisher(KafkaProperties kafkaProperties, ObjectMapper json,
            @Value("${gateway.legacy-json-topic}") String topic) {
        this.kafka = new KafkaTemplate<>(new DefaultKafkaProducerFactory<>(
                kafkaProperties.buildProducerProperties(), new StringSerializer(), new StringSerializer()));
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
