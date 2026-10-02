package com.dss26.core.adapter.mq;

import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;

/**
 * Request/reply over MQ with the core. Messages are fixed-length EBCDIC
 * records laid out by the copybooks in /copybooks; the correlation id ties a
 * reply to its request.
 */
@Component
public class MqGateway {

    private final JmsTemplate jms;

    public MqGateway(JmsTemplate jms) {
        this.jms = jms;
        this.jms.setReceiveTimeout(5_000);
    }

    /**
     * Sends a record and waits for the reply. {@code correlationId} must be
     * unique per business operation: the core treats a repeated id as a
     * duplicate and replays its earlier reply instead of posting twice.
     */
    public byte[] requestReply(String requestQueue, String replyQueue, byte[] record, String correlationId) {
        String mqCorrelId = toMqCorrelId(correlationId);
        jms.send(requestQueue, session -> {
            BytesMessage msg = session.createBytesMessage();
            msg.writeBytes(record);
            msg.setJMSCorrelationID(mqCorrelId);
            msg.setJMSReplyTo(session.createQueue(replyQueue));
            return msg;
        });
        Message reply = jms.receiveSelected(replyQueue, "JMSCorrelationID='" + mqCorrelId + "'");
        if (reply == null) {
            throw new CoreTimeoutException(requestQueue, correlationId);
        }
        try {
            BytesMessage bytes = (BytesMessage) reply;
            byte[] body = new byte[(int) bytes.getBodyLength()];
            bytes.readBytes(body);
            return body;
        } catch (JMSException e) {
            throw new IllegalStateException("Unreadable reply on " + replyQueue, e);
        }
    }

    /** MQ correlation ids are 24 bytes; we use the hex of the first 24 bytes of the business id. */
    static String toMqCorrelId(String businessId) {
        byte[] raw = businessId.replace("-", "").getBytes(StandardCharsets.US_ASCII);
        StringBuilder hex = new StringBuilder("ID:");
        for (int i = 0; i < 24; i++) {
            hex.append(String.format("%02x", i < raw.length ? raw[i] : 0));
        }
        return hex.toString();
    }

    public static class CoreTimeoutException extends RuntimeException {
        public CoreTimeoutException(String queue, String correlationId) {
            super("No reply from the core on " + queue + " for " + correlationId);
        }
    }
}
