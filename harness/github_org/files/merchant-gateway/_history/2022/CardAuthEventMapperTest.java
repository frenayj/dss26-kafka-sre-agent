package com.dss26.payments.gateway.events;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;

import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;
import org.junit.jupiter.api.Test;

import com.dss26.payments.gateway.api.AuthorisationRequest;

class CardAuthEventMapperTest {

    private static final String AUTH_ID = "3f6c2a8e-5d1b-4c7e-9a40-1e8b7d2c6f05";
    private static final Instant RECEIVED_AT = Instant.parse("2022-03-14T09:15:30.123Z");

    private final CardAuthSchema schema = new CardAuthSchema();
    private final CardAuthEventMapper mapper = new CardAuthEventMapper(schema);

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
    }

    @Test
    void eventValidatesAgainstTheSchema() {
        assertThat(GenericData.get().validate(schema.schema(), mapper.toEvent(AUTH_ID, request(), RECEIVED_AT)))
                .isTrue();
    }

    private static AuthorisationRequest request() {
        AuthorisationRequest request = new AuthorisationRequest();
        request.setMerchantId("mch_lumen_coffee");
        request.setCardToken("tok_4410982");
        request.setAmount(new BigDecimal("42.50"));
        request.setCurrency("EUR");
        request.setMerchantCountry("FR");
        return request;
    }
}
