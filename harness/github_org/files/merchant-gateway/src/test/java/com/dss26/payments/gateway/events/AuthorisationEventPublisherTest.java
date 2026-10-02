package com.dss26.payments.gateway.events;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CompletableFuture;

import org.apache.avro.generic.GenericRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.errors.TimeoutException;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

import com.dss26.payments.gateway.GatewayProperties;
import com.dss26.payments.gateway.api.AuthorisationRequest;
import com.dss26.payments.gateway.api.Channel;

class AuthorisationEventPublisherTest {

    @SuppressWarnings("unchecked")
    private final KafkaTemplate<String, GenericRecord> kafka = mock(KafkaTemplate.class);

    private final AuthorisationEventPublisher publisher = new AuthorisationEventPublisher(kafka,
            new GatewayProperties("cards.authorisation.requested.v1", Duration.ofSeconds(2), Duration.ofHours(24),
                    "prod", new GatewayProperties.RateLimit(200, 400)));

    private final GenericRecord event = new CardAuthEventMapper(CardAuthSchema.load(), "prod").toEvent(
            "9a3e51c4-7b20-4f8d-8c61-2d4f0b7e9a13",
            new AuthorisationRequest("mch_lumen_coffee", "tok_4410982", new BigDecimal("42.50"), "EUR", "FR",
                    List.of(), Channel.ECOM),
            Instant.parse("2026-01-14T10:00:00Z"));

    @Test
    @SuppressWarnings("unchecked")
    void publishesKeyedByCardTokenWithTheRequestIdHeader() {
        when(kafka.send(any(ProducerRecord.class))).thenReturn(CompletableFuture.completedFuture(null));

        publisher.publish("tok_4410982", event, "req-20260114-0042");

        ArgumentCaptor<ProducerRecord<String, GenericRecord>> sent = ArgumentCaptor.forClass(ProducerRecord.class);
        verify(kafka).send(sent.capture());
        assertThat(sent.getValue().topic()).isEqualTo("cards.authorisation.requested.v1");
        assertThat(sent.getValue().key()).isEqualTo("tok_4410982");
        assertThat(sent.getValue().headers().lastHeader("x-request-id").value())
                .isEqualTo("req-20260114-0042".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    @SuppressWarnings("unchecked")
    void sendsNoRequestIdHeaderWhenThereIsNone() {
        when(kafka.send(any(ProducerRecord.class))).thenReturn(CompletableFuture.completedFuture(null));

        publisher.publish("tok_4410982", event, null);

        ArgumentCaptor<ProducerRecord<String, GenericRecord>> sent = ArgumentCaptor.forClass(ProducerRecord.class);
        verify(kafka).send(sent.capture());
        assertThat(sent.getValue().headers().lastHeader("x-request-id")).isNull();
    }

    @Test
    @SuppressWarnings("unchecked")
    void aFailedSendBecomesPublishFailed() {
        when(kafka.send(any(ProducerRecord.class))).thenReturn(
                CompletableFuture.<SendResult<String, GenericRecord>>failedFuture(new TimeoutException("no ack")));

        assertThatThrownBy(() -> publisher.publish("tok_4410982", event, null))
                .isInstanceOf(PublishFailedException.class);
    }
}
