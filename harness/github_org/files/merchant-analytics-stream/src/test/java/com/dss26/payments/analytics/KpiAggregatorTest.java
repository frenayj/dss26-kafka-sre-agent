package com.dss26.payments.analytics;

import com.dss26.payments.CardAuthEvent;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class KpiAggregatorTest {

    private static CardAuthEvent auth(double amount, String currency, String channel, List<String> signals) {
        return CardAuthEvent.newBuilder()
                .setAuthId("a3c1e9a0-6a43-4f0e-8a51-2d6b0b7f4c21")
                .setCardToken("tok_9b31d2")
                .setMerchantId("MRC-0042817")
                .setAmount(amount)
                .setCurrency(currency)
                .setCountry("NL")
                .setTs(Instant.parse("2026-02-10T13:00:00Z"))
                .setRiskSignals(signals)
                .setChannel(channel)
                .setTier("prod")
                .build();
    }

    @Test
    void countsAndSumsPerCurrency() {
        MerchantKpi kpi = KpiAggregator.empty();
        kpi = KpiAggregator.add(kpi, auth(20.0, "EUR", "ECOM", List.of()));
        kpi = KpiAggregator.add(kpi, auth(30.0, "EUR", "CARD_PRESENT", List.of()));
        kpi = KpiAggregator.add(kpi, auth(15.0, "GBP", "ECOM", List.of()));

        assertEquals(3L, kpi.getAuthCount());
        assertEquals(50.0, kpi.getAmountByCurrency().get("EUR"), 1e-9);
        assertEquals(15.0, kpi.getAmountByCurrency().get("GBP"), 1e-9);
        assertEquals(30.0, kpi.getMaxAmount(), 1e-9);
    }

    @Test
    void tracksChannelMix() {
        MerchantKpi kpi = KpiAggregator.empty();
        kpi = KpiAggregator.add(kpi, auth(10.0, "EUR", "ECOM", List.of()));
        kpi = KpiAggregator.add(kpi, auth(10.0, "EUR", "ECOM", List.of()));
        kpi = KpiAggregator.add(kpi, auth(10.0, "EUR", "RECURRING", List.of()));

        assertEquals(2L, kpi.getChannelCounts().get("ECOM"));
        assertEquals(1L, kpi.getChannelCounts().get("RECURRING"));
    }

    @Test
    void countsRiskFlaggedRequests() {
        MerchantKpi kpi = KpiAggregator.empty();
        kpi = KpiAggregator.add(kpi, auth(10.0, "EUR", "ECOM", List.of("VELOCITY_HIGH")));
        kpi = KpiAggregator.add(kpi, auth(10.0, "EUR", "ECOM", List.of()));

        assertEquals(1L, kpi.getRiskFlaggedCount());
    }
}
