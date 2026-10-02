package com.dss26.cards.clearing.matching;

import com.dss26.cards.clearing.Topics;
import com.dss26.cards.events.ClearingMatched;
import com.dss26.cards.events.ClearingReceived;
import org.apache.avro.specific.SpecificRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Clock;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

@Component
public class ClearingMatcher {

    private static final Logger log = LoggerFactory.getLogger(ClearingMatcher.class);

    record Candidate(MatchScorer.Authorisation auth, double score) {
    }

    private final AuthorisationLog authorisations;
    private final NamedParameterJdbcTemplate jdbc;
    private final KafkaTemplate<String, SpecificRecord> kafka;
    private final Clock clock;

    public ClearingMatcher(AuthorisationLog authorisations, NamedParameterJdbcTemplate jdbc,
                           KafkaTemplate<String, SpecificRecord> kafka, Clock clock) {
        this.authorisations = authorisations;
        this.jdbc = jdbc;
        this.kafka = kafka;
        this.clock = clock;
    }

    @Transactional
    @KafkaListener(id = "matcher", topics = Topics.CLEARING_RECEIVED, groupId = "clearing-settlement-matcher")
    public void onClearingReceived(ClearingReceived clearing) {
        MapSqlParameterSource id = new MapSqlParameterSource("id", clearing.getClearingId());
        List<String> mcc = jdbc.queryForList("SELECT mcc FROM clearing_record WHERE clearing_id = :id", id, String.class);
        MatchScorer.Presentment presentment = new MatchScorer.Presentment(clearing.getCardToken(),
                clearing.getMerchantId(), mcc.isEmpty() ? "" : mcc.get(0),
                BigDecimal.valueOf(clearing.getAmount()), clearing.getCurrency());

        Optional<Candidate> best = authorisations.candidates(clearing.getCardToken(), clearing.getMerchantId())
                .stream()
                .map(a -> new Candidate(a, MatchScorer.score(presentment, a)))
                .filter(c -> c.score() >= MatchScorer.MATCH_THRESHOLD)
                .max(Comparator.comparingDouble(Candidate::score));

        if (best.isEmpty()) {
            jdbc.update("UPDATE clearing_record SET status = 'UNMATCHED' WHERE clearing_id = :id", id);
            log.info("No authorisation for clearing {} - routed to exceptions", clearing.getClearingId());
            return;
        }

        MatchScorer.Authorisation auth = best.get().auth();
        double authAmount = auth.amount().doubleValue();
        jdbc.update("INSERT INTO clearing_match (clearing_id, auth_id, score) VALUES (:id, :auth, :score)",
                new MapSqlParameterSource("id", clearing.getClearingId())
                        .addValue("auth", auth.authId())
                        .addValue("score", best.get().score()));
        kafka.send(Topics.CLEARING_MATCHED, clearing.getClearingId(), ClearingMatched.newBuilder()
                .setClearingId(clearing.getClearingId())
                .setAuthId(auth.authId())
                .setAuthAmount(authAmount)
                .setClearingAmount(clearing.getAmount())
                .setAmountDelta(clearing.getAmount() - authAmount)
                .setMatchConfidence(best.get().score())
                .setMatchedAt(clock.instant())
                .build());
    }
}
