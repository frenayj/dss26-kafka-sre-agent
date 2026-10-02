package com.dss26.cards.clearing.matching;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Set;

/**
 * Scores how well a presentment matches a candidate authorisation from the
 * issuer authorisation log. Same card and merchant are prerequisites; the
 * score then reflects how far the cleared amount is from the authorised one.
 */
public final class MatchScorer {

    /** Hotels, car hire, restaurants and bars: final amount legitimately differs (tips, incidentals). */
    static final Set<String> TOLERANT_MCCS = Set.of("7011", "7512", "5812", "5813");
    static final BigDecimal DEFAULT_TOLERANCE = new BigDecimal("0.00");
    static final BigDecimal HOSPITALITY_TOLERANCE = new BigDecimal("0.15");
    public static final double MATCH_THRESHOLD = 0.8;

    public record Presentment(String cardToken, String merchantId, String mcc, BigDecimal amount, String currency) {
    }

    public record Authorisation(String authId, String cardToken, String merchantId, BigDecimal amount, String currency) {
    }

    private MatchScorer() {
    }

    public static double score(Presentment p, Authorisation a) {
        if (!p.cardToken().equals(a.cardToken()) || !p.merchantId().equals(a.merchantId())
                || !p.currency().equals(a.currency())) {
            return 0.0;
        }
        if (p.amount().compareTo(a.amount()) == 0) {
            return 1.0;
        }
        if (a.amount().signum() == 0) {
            return 0.0;
        }
        BigDecimal delta = p.amount().subtract(a.amount()).abs()
                .divide(a.amount(), 4, RoundingMode.HALF_UP);
        BigDecimal tolerance = TOLERANT_MCCS.contains(p.mcc()) ? HOSPITALITY_TOLERANCE : DEFAULT_TOLERANCE;
        if (delta.compareTo(tolerance) > 0) {
            return 0.0;
        }
        // Inside tolerance: 0.95 at a tiny delta down to 0.8 at the limit.
        return 0.95 - 0.15 * delta.doubleValue() / tolerance.doubleValue();
    }
}
