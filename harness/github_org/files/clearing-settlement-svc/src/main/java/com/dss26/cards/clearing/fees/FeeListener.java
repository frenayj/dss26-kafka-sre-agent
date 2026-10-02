package com.dss26.cards.clearing.fees;

import com.dss26.cards.clearing.Topics;
import com.dss26.cards.events.CardNetwork;
import com.dss26.cards.events.ClearingMatched;
import com.dss26.cards.events.InterchangeFeeCalculated;
import org.apache.avro.specific.SpecificRecord;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.time.Clock;

@Component
public class FeeListener {

    private final NamedParameterJdbcTemplate jdbc;
    private final KafkaTemplate<String, SpecificRecord> kafka;
    private final Clock clock;

    public FeeListener(NamedParameterJdbcTemplate jdbc, KafkaTemplate<String, SpecificRecord> kafka, Clock clock) {
        this.jdbc = jdbc;
        this.kafka = kafka;
        this.clock = clock;
    }

    record ClearingRow(String network, String cardProduct, String region, boolean cardPresent, String currency) {
    }

    @KafkaListener(id = "fees", topics = Topics.CLEARING_MATCHED, groupId = "clearing-settlement-fees")
    public void onClearingMatched(ClearingMatched matched) {
        MapSqlParameterSource id = new MapSqlParameterSource("id", matched.getClearingId());
        ClearingRow row = jdbc.queryForObject("""
                SELECT network, card_product, region, card_present, currency
                  FROM clearing_record WHERE clearing_id = :id
                """, id, new DataClassRowMapper<>(ClearingRow.class));

        InterchangeCalculator.FeeBreakdown fees = InterchangeCalculator.calculate(
                CardNetwork.valueOf(row.network()), CardProduct.valueOf(row.cardProduct()),
                InterchangeCalculator.Region.valueOf(row.region()), row.cardPresent(),
                BigDecimal.valueOf(matched.getClearingAmount()));

        jdbc.update("UPDATE clearing_record SET fee_total = :fee, status = 'CLEARED' WHERE clearing_id = :id",
                id.addValue("fee", fees.total()));

        kafka.send(Topics.INTERCHANGE_FEE, matched.getClearingId(), InterchangeFeeCalculated.newBuilder()
                .setClearingId(matched.getClearingId())
                .setAuthId(matched.getAuthId())
                .setInterchangeFee(fees.interchange().doubleValue())
                .setSchemeFee(fees.schemeFee().doubleValue())
                .setAcquirerMarkup(fees.acquirerMarkup().doubleValue())
                .setTotalFee(fees.total().doubleValue())
                .setCurrency(row.currency())
                .setInterchangeProgram(fees.program())
                .setCalculatedAt(clock.instant())
                .build());
    }
}
