package com.dss26.cards.statements.job;

import com.dss26.cards.statements.job.Model.CardStatement;
import com.dss26.cards.statements.job.Model.StatementCycle;
import com.dss26.cards.statements.job.Model.StatementLine;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class StatementItemProcessorTest {

    private static final StatementCycle CYCLE =
            new StatementCycle("tok_8c2d71", "CUST-40311", "2026-08", new BigDecimal("120.00"), "EUR");

    private static StatementLine line(String amount, String status) {
        return new StatementLine("auth-" + amount, "MRC-0005521", new BigDecimal(amount), status,
                Instant.parse("2026-08-14T10:30:00Z"));
    }

    @Test
    void closingBalanceIgnoresReversals() {
        StatementItemProcessor processor = new StatementItemProcessor((card, period) -> List.of(
                line("45.10", "SETTLED"), line("19.90", "REVERSED"), line("7.50", "PENDING")));
        CardStatement statement = processor.process(CYCLE);
        assertThat(statement.closingBalance()).isEqualByComparingTo("172.60");
        assertThat(statement.lines()).hasSize(3);
    }

    @Test
    void inactiveCardWithNothingOwedGetsNoStatement() {
        StatementItemProcessor processor = new StatementItemProcessor((card, period) -> List.of());
        StatementCycle zero = new StatementCycle("tok_8c2d71", "CUST-40311", "2026-08", BigDecimal.ZERO, "EUR");
        assertThat(processor.process(zero)).isNull();
    }
}
