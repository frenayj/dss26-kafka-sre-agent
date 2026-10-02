package com.dss26.cards.statements.job;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class Model {

    private Model() {
    }

    /** One card's statement cycle, as the reader hands it out. */
    public record StatementCycle(String cardToken, String customerId, String period, BigDecimal openingBalance,
                                 String currency) {
    }

    public record StatementLine(String authId, String merchantId, BigDecimal amount, String status,
                                Instant authorisedAt) {
    }

    public record CardStatement(String statementId, StatementCycle cycle, List<StatementLine> lines,
                                BigDecimal closingBalance) {
    }
}
