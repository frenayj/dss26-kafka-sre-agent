package com.dss26.cards.clearing.fees;

import com.dss26.cards.events.CardNetwork;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Interchange, scheme fee and acquirer markup for one cleared transaction.
 *
 * Intra-EEA consumer cards are capped by the Interchange Fee Regulation
 * (EU 2015/751): 0.2% debit, 0.3% credit. Inter-regional consumer rates follow
 * the schemes' 2019 commitments to the Commission (card-present 0.2% / 0.3%,
 * card-not-present 1.15% / 1.50%). Commercial cards are not capped; we use the
 * scheme table rate.
 */
public final class InterchangeCalculator {

    public enum Region { INTRA_EEA, INTER_REGIONAL }

    public record FeeBreakdown(BigDecimal interchange, BigDecimal schemeFee, BigDecimal acquirerMarkup,
                               BigDecimal total, String program) {
    }

    static final BigDecimal ACQUIRER_MARKUP = new BigDecimal("0.0015");

    private InterchangeCalculator() {
    }

    public static FeeBreakdown calculate(CardNetwork network, CardProduct product, Region region,
                                         boolean cardPresent, BigDecimal amount) {
        BigDecimal rate = interchangeRate(product, region, cardPresent);
        BigDecimal interchange = money(amount.multiply(rate));
        BigDecimal scheme = money(amount.multiply(schemeRate(network)));
        BigDecimal markup = money(amount.multiply(ACQUIRER_MARKUP));
        return new FeeBreakdown(interchange, scheme, markup, interchange.add(scheme).add(markup),
                program(product, region, cardPresent));
    }

    static BigDecimal interchangeRate(CardProduct product, Region region, boolean cardPresent) {
        return switch (product) {
            case CONSUMER_DEBIT -> region == Region.INTRA_EEA || cardPresent
                    ? new BigDecimal("0.0020") : new BigDecimal("0.0115");
            case CONSUMER_CREDIT -> region == Region.INTRA_EEA || cardPresent
                    ? new BigDecimal("0.0030") : new BigDecimal("0.0150");
            case COMMERCIAL -> new BigDecimal("0.0120");
        };
    }

    static BigDecimal schemeRate(CardNetwork network) {
        return switch (network) {
            case VISA -> new BigDecimal("0.0002");
            case MASTERCARD -> new BigDecimal("0.00025");
            default -> new BigDecimal("0.0005");
        };
    }

    static String program(CardProduct product, Region region, boolean cardPresent) {
        String base = region == Region.INTRA_EEA ? "EEA-IFR" : (cardPresent ? "INTER-CP" : "INTER-CNP");
        return base + "/" + product.name().replace('_', '-');
    }

    private static BigDecimal money(BigDecimal value) {
        return value.setScale(2, RoundingMode.HALF_EVEN);
    }
}
