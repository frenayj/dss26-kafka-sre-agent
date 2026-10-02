package com.dss26.cards.statements.job;

import com.dss26.cards.statements.job.Model.StatementLine;

import java.time.YearMonth;
import java.util.List;

/** Where a card's transactions for a period come from (the txn-history read replica in production). */
@FunctionalInterface
public interface StatementLines {
    List<StatementLine> forCard(String cardToken, YearMonth period);
}
