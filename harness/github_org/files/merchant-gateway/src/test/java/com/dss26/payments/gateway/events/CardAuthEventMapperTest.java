package com.dss26.payments.gateway.events;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;
import org.junit.jupiter.api.Test;

import com.dss26.payments.gateway.api.AuthorisationRequest;
import com.dss26.payments.gateway.api.Channel;

class CardAuthEventMapperTest {

    private static final String AUTH_ID = "3f6c2a8e-5d1b-4c7e-9a40-1e8b7d2c6f05";
    private static final Instant RECEIVED_AT = Instant.parse("2022-03-14T09:15:30.123Z");

    private final Schema schema = CardAuthSchema.load();
    private final CardAuthEventMapper mapper = new CardAuthEventMapper(schema, "prod");

    @Test
    void loadsTheCardAuthEventSchemaFromTheClasspath() {
        assertThat(schema.getFullName()).isEqualTo("com.dss26.payments.CardAuthEvent");
    }

    @Test
    void mapsAnAcceptedRequestOntoTheEvent() {
        GenericRecord event = mapper.toEvent(AUTH_ID, request(), RECEIVED_AT);

        assertThat(event.get("auth_id")).isEqualTo(AUTH_ID);
        assertThat(event.get("card_token")).isEqualTo("tok_4410982");
        assertThat(event.get("merchant_id")).isEqualTo("mch_lumen_coffee");
        assertThat(event.get("amount")).isEqualTo(42.5);
        assertThat(event.get("currency")).isEqualTo("EUR");
        assertThat(event.get("country")).isEqualTo("FR");
        assertThat(event.get("ts")).isEqualTo(RECEIVED_AT.toEpochMilli());
        assertThat(event.get("risk_signals")).isEqualTo(List.of("VELOCITY_OK"));
        assertThat(event.get("channel")).isEqualTo("CARD_PRESENT");
        assertThat(event.get("tier")).isEqualTo("prod");
    }

    @Test
    void channelDefaultsToEcom() {
        AuthorisationRequest noChannel = new AuthorisationRequest("mch_lumen_coffee", "tok_4410982",
                new BigDecimal("9.99"), "EUR", "FR", List.of(), null);

        assertThat(mapper.toEvent(AUTH_ID, noChannel, RECEIVED_AT).get("channel")).isEqualTo("ECOM");
    }

    @Test
    void eventValidatesAgainstTheSchema() {
        assertThat(GenericData.get().validate(schema, mapper.toEvent(AUTH_ID, request(), RECEIVED_AT))).isTrue();
    }

    private static AuthorisationRequest request() {
        return new AuthorisationRequest(
                "mch_lumen_coffee",
                "tok_4410982",
                new BigDecimal("42.50"),
                "EUR",
                "FR",
                List.of("VELOCITY_OK"),
                Channel.CARD_PRESENT);
    }
}
