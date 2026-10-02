package com.dss26.payments.gateway.events;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.avro.generic.GenericRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import com.dss26.payments.gateway.GatewayProperties;

@Component
public class AuthorisationEventPublisher {

    static final String REQUEST_ID_HEADER = "x-request-id";

    private static final Logger log = LoggerFactory.getLogger(AuthorisationEventPublisher.class);

    private final KafkaTemplate<String, GenericRecord> kafka;
    private final String topic;
    private final Duration sendTimeout;

    public AuthorisationEventPublisher(KafkaTemplate<String, GenericRecord> kafka, GatewayProperties properties) {
        this.kafka = kafka;
        this.topic = properties.topic();
        this.sendTimeout = properties.sendTimeout();
    }

    /**
     * Publishes the event keyed by card token and waits for the acknowledgement
     * (acks=all), so a 202 to the merchant means the authorisation is on the topic.
     */
    public void publish(String key, GenericRecord event, String requestId) {
        ProducerRecord<String, GenericRecord> record = new ProducerRecord<>(topic, key, event);
        if (requestId != null && !requestId.isBlank()) {
            record.headers().add(REQUEST_ID_HEADER, requestId.getBytes(StandardCharsets.UTF_8));
        }
        try {
            kafka.send(record).get(sendTimeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new PublishFailedException("Interrupted publishing auth_id " + event.get("auth_id"), e);
        } catch (ExecutionException | TimeoutException e) {
            log.error("Publishing auth_id={} to {} failed", event.get("auth_id"), topic, e);
            throw new PublishFailedException("Could not publish auth_id " + event.get("auth_id"), e);
        }
    }
}
