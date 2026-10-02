package com.dss26.cards.disputes.chargeback;

import com.dss26.cards.events.ChargebackCategory;
import com.dss26.cards.events.ChargebackOutcome;

import java.math.BigDecimal;
import java.time.Instant;

public record Chargeback(
        String id,
        String authId,
        String merchantId,
        CardNetwork network,
        BigDecimal disputedAmount,
        String currency,
        String reasonCode,
        ChargebackCategory category,
        Instant openedAt,
        ChargebackOutcome outcome,
        BigDecimal recoveredAmount,
        Instant resolvedAt) {

    public boolean isOpen() {
        return outcome == null;
    }
}
