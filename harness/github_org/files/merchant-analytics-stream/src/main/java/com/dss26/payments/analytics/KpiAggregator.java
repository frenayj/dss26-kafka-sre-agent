package com.dss26.payments.analytics;

import com.dss26.payments.CardAuthEvent;

import java.util.HashMap;
import java.util.Map;

/** Pure aggregation logic, kept out of the topology so it can be tested without Kafka. */
public final class KpiAggregator {

    private KpiAggregator() {
    }

    public static MerchantKpi empty() {
        return MerchantKpi.newBuilder()
                .setAuthCount(0L)
                .setAmountByCurrency(new HashMap<>())
                .setMaxAmount(0.0)
                .setChannelCounts(new HashMap<>())
                .setRiskFlaggedCount(0L)
                .build();
    }

    public static MerchantKpi add(MerchantKpi kpi, CardAuthEvent auth) {
        Map<String, Double> amounts = new HashMap<>(kpi.getAmountByCurrency());
        amounts.merge(auth.getCurrency(), auth.getAmount(), Double::sum);

        Map<String, Long> channels = new HashMap<>(kpi.getChannelCounts());
        channels.merge(auth.getChannel(), 1L, Long::sum);

        boolean flagged = auth.getRiskSignals() != null && !auth.getRiskSignals().isEmpty();

        return MerchantKpi.newBuilder(kpi)
                .setAuthCount(kpi.getAuthCount() + 1)
                .setAmountByCurrency(amounts)
                .setMaxAmount(Math.max(kpi.getMaxAmount(), auth.getAmount()))
                .setChannelCounts(channels)
                .setRiskFlaggedCount(kpi.getRiskFlaggedCount() + (flagged ? 1 : 0))
                .build();
    }

    /** Average ticket for one currency, 0 when the merchant took none in that currency. */
    public static double averageTicket(MerchantKpi kpi, String currency, long countInCurrency) {
        Double total = kpi.getAmountByCurrency().get(currency);
        if (total == null || countInCurrency == 0) {
            return 0.0;
        }
        return total / countInCurrency;
    }
}
