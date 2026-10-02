package com.dss26.cards.statements.job;

import com.dss26.cards.statements.job.Model.CardStatement;
import com.dss26.cards.statements.job.Model.StatementCycle;
import com.dss26.cards.statements.job.Model.StatementLine;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.time.YearMonth;
import java.util.List;
import java.util.UUID;

/**
 * Builds one card's statement. Reversed authorisations are listed but do not
 * count towards the balance. A card with no activity and nothing owed gets no
 * statement (returning null filters the item).
 */
@Component
public class StatementItemProcessor implements ItemProcessor<StatementCycle, CardStatement> {

    private final StatementLines lines;

    public StatementItemProcessor(StatementLines lines) {
        this.lines = lines;
    }

    @Override
    public CardStatement process(StatementCycle cycle) {
        List<StatementLine> items = lines.forCard(cycle.cardToken(), YearMonth.parse(cycle.period()));
        if (items.isEmpty() && cycle.openingBalance().signum() == 0) {
            return null;
        }
        BigDecimal spent = items.stream()
                .filter(l -> !"REVERSED".equals(l.status()))
                .map(StatementLine::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        return new CardStatement(UUID.randomUUID().toString(), cycle, items, cycle.openingBalance().add(spent));
    }
}
