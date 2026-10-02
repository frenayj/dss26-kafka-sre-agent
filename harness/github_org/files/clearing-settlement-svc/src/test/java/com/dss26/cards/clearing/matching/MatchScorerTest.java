package com.dss26.cards.clearing.matching;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

class MatchScorerTest {

    private static MatchScorer.Presentment presentment(String mcc, String amount) {
        return new MatchScorer.Presentment("tok_77ac01", "MRC-0007311", mcc, new BigDecimal(amount), "EUR");
    }

    private static final MatchScorer.Authorisation AUTH =
            new MatchScorer.Authorisation("auth-1", "tok_77ac01", "MRC-0007311", new BigDecimal("100.00"), "EUR");

    @Test
    void exactAmountIsACertainMatch() {
        assertThat(MatchScorer.score(presentment("5411", "100.00"), AUTH)).isEqualTo(1.0);
    }

    @Test
    void groceryClearingThatDiffersDoesNotMatch() {
        assertThat(MatchScorer.score(presentment("5411", "101.00"), AUTH)).isZero();
    }

    @Test
    void restaurantTipWithinFifteenPercentMatches() {
        assertThat(MatchScorer.score(presentment("5812", "112.00"), AUTH))
                .isGreaterThanOrEqualTo(MatchScorer.MATCH_THRESHOLD);
    }

    @Test
    void differentCardNeverMatches() {
        var other = new MatchScorer.Authorisation("auth-2", "tok_000000", "MRC-0007311", new BigDecimal("100.00"), "EUR");
        assertThat(MatchScorer.score(presentment("5411", "100.00"), other)).isZero();
    }
}
