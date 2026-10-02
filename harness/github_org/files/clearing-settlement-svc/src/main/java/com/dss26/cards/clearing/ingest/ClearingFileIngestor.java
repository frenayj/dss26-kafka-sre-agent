package com.dss26.cards.clearing.ingest;

import com.dss26.cards.clearing.Topics;
import com.dss26.cards.events.CardNetwork;
import com.dss26.cards.events.ClearingReceived;
import org.apache.avro.specific.SpecificRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.sql.Timestamp;
import java.time.Clock;
import java.util.List;

/**
 * Picks up the normalised presentment files the scheme gateway drops on the
 * MFT share (one per network per clearing cycle: Visa Base II, Mastercard
 * IPM), stores each presentment and publishes it to cards.clearing.received.v1.
 *
 * Line format (pipe-separated, header line starts with '#'):
 *   clearing_id|network|network_reference|card_token|merchant_id|mcc|amount|currency|card_product
 */
@Component
public class ClearingFileIngestor {

    private static final Logger log = LoggerFactory.getLogger(ClearingFileIngestor.class);

    private static final String INSERT = """
            INSERT INTO clearing_record (clearing_id, network, network_reference, card_token, merchant_id,
                                         mcc, amount, currency, card_product, received_at)
            VALUES (:id, :network, :ref, :card, :merchant, :mcc, :amount, :currency, :product, :receivedAt)
            ON CONFLICT (clearing_id) DO NOTHING
            """;

    private final Path inbox;
    private final Path done;
    private final NamedParameterJdbcTemplate jdbc;
    private final KafkaTemplate<String, SpecificRecord> kafka;
    private final Clock clock;

    public ClearingFileIngestor(@Value("${clearing.inbox}") Path inbox, @Value("${clearing.done}") Path done,
                                NamedParameterJdbcTemplate jdbc, KafkaTemplate<String, SpecificRecord> kafka, Clock clock) {
        this.inbox = inbox;
        this.done = done;
        this.jdbc = jdbc;
        this.kafka = kafka;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${clearing.poll-interval:PT1M}")
    public void poll() throws IOException {
        try (DirectoryStream<Path> files = Files.newDirectoryStream(inbox, "*.{base2,ipm}.psv")) {
            for (Path file : files) {
                ingest(file);
                Files.move(file, done.resolve(file.getFileName()), StandardCopyOption.ATOMIC_MOVE);
            }
        }
    }

    void ingest(Path file) throws IOException {
        List<String> lines = Files.readAllLines(file);
        int published = 0;
        for (String line : lines) {
            if (line.isBlank() || line.startsWith("#")) {
                continue;
            }
            String[] f = line.split("\\|", -1);
            int inserted = jdbc.update(INSERT, new MapSqlParameterSource()
                    .addValue("id", f[0]).addValue("network", f[1]).addValue("ref", f[2]).addValue("card", f[3])
                    .addValue("merchant", f[4]).addValue("mcc", f[5]).addValue("amount", new BigDecimal(f[6]))
                    .addValue("currency", f[7]).addValue("product", f[8])
                    .addValue("receivedAt", Timestamp.from(clock.instant())));
            if (inserted == 0) {
                continue; // file re-delivered by the gateway
            }
            kafka.send(Topics.CLEARING_RECEIVED, f[0], ClearingReceived.newBuilder()
                    .setClearingId(f[0])
                    .setNetwork(CardNetwork.valueOf(f[1]))
                    .setNetworkReference(f[2])
                    .setCardToken(f[3])
                    .setMerchantId(f[4])
                    .setAmount(Double.parseDouble(f[6]))
                    .setCurrency(f[7])
                    .setReceivedAt(clock.instant())
                    .build());
            published++;
        }
        log.info("Ingested {}: {} presentments published", file.getFileName(), published);
    }
}
