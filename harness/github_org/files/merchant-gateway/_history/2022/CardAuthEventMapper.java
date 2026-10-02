package com.dss26.payments.gateway.events;

import java.time.Instant;

import org.apache.avro.Schema;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.generic.GenericRecordBuilder;
import org.springframework.stereotype.Component;

import com.dss26.payments.gateway.api.AuthorisationRequest;

/**
 * Builds the cards.authorisation.requested.v1 value for an accepted request.
 * Field names and types are those of src/main/avro/cards.authorisation.requested.v1.avsc.
 */
@Component
public class CardAuthEventMapper {

    private final Schema schema;

    public CardAuthEventMapper(CardAuthSchema schema) {
        this.schema = schema.schema();
    }

    public GenericRecord toEvent(String authId, AuthorisationRequest request, Instant receivedAt) {
        return new GenericRecordBuilder(schema)
                .set("auth_id", authId)
                .set("card_token", request.getCardToken())
                .set("merchant_id", request.getMerchantId())
                .set("amount", request.getAmount().doubleValue())
                .set("currency", request.getCurrency())
                .set("country", request.getMerchantCountry())
                .set("ts", receivedAt.toEpochMilli())
                .build();
    }
}
