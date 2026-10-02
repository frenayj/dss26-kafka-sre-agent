package com.dss26.cards.clearing.settlement;

import com.dss26.cards.clearing.Topics;
import com.dss26.cards.events.SettlementBatchPosted;
import com.dss26.ledger.events.JournalPosted;
import org.apache.avro.specific.SpecificRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.UUID;

/**
 * Daily cut-off at 22:00 Paris time: one batch per merchant and currency over
 * everything CLEARED since the last cut-off, then the GL journal for it.
 */
@Component
public class SettlementBatchJob {

    private static final Logger log = LoggerFactory.getLogger(SettlementBatchJob.class);
    private static final ZoneId PARIS = ZoneId.of("Europe/Paris");

    static final String GL_MERCHANT_PAYABLE = "2310-MERCHANT-PAYABLE";
    static final String GL_SCHEME_CLEARING = "1420-SCHEME-CLEARING";

    record MerchantTotals(String merchantId, String currency, BigDecimal gross, BigDecimal fees, int count) {
    }

    private final NamedParameterJdbcTemplate jdbc;
    private final KafkaTemplate<String, SpecificRecord> kafka;
    private final Clock clock;

    public SettlementBatchJob(NamedParameterJdbcTemplate jdbc, KafkaTemplate<String, SpecificRecord> kafka, Clock clock) {
        this.jdbc = jdbc;
        this.kafka = kafka;
        this.clock = clock;
    }

    @Scheduled(cron = "0 0 22 * * MON-FRI", zone = "Europe/Paris")
    @Transactional
    public void cutOff() {
        LocalDate settlementDate = LocalDate.now(clock.withZone(PARIS));
        if (!TargetCalendar.isBusinessDay(settlementDate)) {
            log.info("{} is a TARGET closing day - no settlement run", settlementDate);
            return;
        }
        List<MerchantTotals> totals = jdbc.query("""
                SELECT merchant_id, currency, SUM(amount) AS gross, SUM(fee_total) AS fees, COUNT(*) AS count
                  FROM clearing_record
                 WHERE status = 'CLEARED' AND settlement_batch_id IS NULL
                 GROUP BY merchant_id, currency
                """, new DataClassRowMapper<>(MerchantTotals.class));

        for (MerchantTotals t : totals) {
            String batchId = UUID.randomUUID().toString();
            BigDecimal net = t.gross().subtract(t.fees());
            jdbc.update("""
                    UPDATE clearing_record SET settlement_batch_id = :batch, status = 'SETTLED'
                     WHERE merchant_id = :merchant AND currency = :currency
                       AND status = 'CLEARED' AND settlement_batch_id IS NULL
                    """, new MapSqlParameterSource("batch", batchId)
                    .addValue("merchant", t.merchantId())
                    .addValue("currency", t.currency()));

            kafka.send(Topics.SETTLEMENT_BATCH, t.merchantId(), SettlementBatchPosted.newBuilder()
                    .setBatchId(batchId)
                    .setMerchantId(t.merchantId())
                    .setSettlementDate(settlementDate.toString())
                    .setGrossAmount(t.gross().doubleValue())
                    .setFeesAmount(t.fees().doubleValue())
                    .setNetAmount(net.doubleValue())
                    .setCurrency(t.currency())
                    .setTransactionCount(t.count())
                    .setPostedAt(clock.instant())
                    .build());

            kafka.send(Topics.LEDGER_JOURNAL, batchId, JournalPosted.newBuilder()
                    .setJournalId(UUID.randomUUID().toString())
                    .setSourceSystem("clearing-settlement-svc")
                    .setSourceReference(batchId)
                    .setDebitAccount(GL_SCHEME_CLEARING)
                    .setCreditAccount(GL_MERCHANT_PAYABLE)
                    .setAmount(net.doubleValue())
                    .setCurrency(t.currency())
                    .setValueDate(settlementDate.toString())
                    .setPostedAt(clock.instant())
                    .build());
        }
        log.info("Settlement {}: {} merchant batches posted", settlementDate, totals.size());
    }
}
