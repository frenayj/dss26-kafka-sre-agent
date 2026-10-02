package com.dss26.payments.gateway.events;

/**
 * Kafka did not acknowledge the event in time. The merchant gets a 503 and retries.
 */
public class PublishFailedException extends RuntimeException {

    public PublishFailedException(String message, Throwable cause) {
        super(message, cause);
    }
}
