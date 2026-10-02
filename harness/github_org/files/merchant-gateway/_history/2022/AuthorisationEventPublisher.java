package com.dss26.payments.gateway.events;

import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.avro.generic.GenericRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class AuthorisationEventPublisher {

    private static final Logger log = LoggerFactory.getLogger(AuthorisationEventPublisher.class);

    private final KafkaTemplate<String, GenericRecord> kafka;
    private final String topic;
    private final Duration sendTimeout;

    public AuthorisationEventPublisher(KafkaTemplate<String, GenericRecord> kafka,
            @Value("${gateway.topic}") String topic,
            @Value("${gateway.send-timeout}") Duration sendTimeout) {
        this.kafka = kafka;
        this.topic = topic;
        this.sendTimeout = sendTimeout;
    }

    /**
     * Publishes the event keyed by card token and waits for the acknowledgement
     * (acks=all), so a 202 to the merchant means the authorisation is on the topic.
     */
    public void publish(String key, GenericRecord event) {
        try {
            kafka.send(topic, key, event).get(sendTimeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new PublishFailedException("Interrupted publishing auth_id " + event.get("auth_id"), e);
        } catch (ExecutionException | TimeoutException e) {
            log.error("Publishing auth_id={} to {} failed", event.get("auth_id"), topic, e);
            throw new PublishFailedException("Could not publish auth_id " + event.get("auth_id"), e);
        }
    }
}
