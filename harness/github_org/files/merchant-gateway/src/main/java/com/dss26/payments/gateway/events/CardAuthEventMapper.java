package com.dss26.payments.gateway.events;

import java.time.Instant;

import org.apache.avro.Schema;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.generic.GenericRecordBuilder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import com.dss26.payments.gateway.GatewayProperties;
import com.dss26.payments.gateway.api.AuthorisationRequest;

/**
 * Builds the cards.authorisation.requested.v1 value for an accepted request.
 * Field names and types are those of src/main/avro/cards.authorisation.requested.v1.avsc.
 */
@Component
public class CardAuthEventMapper {

    private final Schema schema;
    private final String tier;

    @Autowired
    public CardAuthEventMapper(CardAuthSchema schema, GatewayProperties properties) {
        this(schema.schema(), properties.tier());
    }

    public CardAuthEventMapper(Schema schema, String tier) {
        this.schema = schema;
        this.tier = tier;
    }

    public GenericRecord toEvent(String authId, AuthorisationRequest request, Instant receivedAt) {
        return new GenericRecordBuilder(schema)
                .set("auth_id", authId)
                .set("card_token", request.cardToken())
                .set("merchant_id", request.merchantId())
                .set("amount", request.amount().doubleValue())
                .set("currency", request.currency())
                .set("country", request.merchantCountry())
                .set("ts", receivedAt.toEpochMilli())
                .set("risk_signals", request.riskSignals())
                .set("channel", request.channel().name())
                .set("tier", tier)
                .build();
    }
}
