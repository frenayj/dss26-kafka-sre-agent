package com.dss26.payments.hub.routing;

import com.dss26.payments.hub.iban.Iban;

import java.math.BigDecimal;
import java.util.Set;

/**
 * Picks the clearing scheme for an outgoing credit transfer.
 *
 * Since the Instant Payments Regulation (EU) 2024/886 applies to us
 * (9 October 2025), an instant payment must cost the customer no more than a
 * standard one, and the SCT Inst scheme no longer caps the amount.
 */
public final class SchemeRouter {

    /** SEPA scheme countries we reach (EEA plus CH, GB and the microstates). */
    static final Set<String> SEPA = Set.of(
            "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", "GR", "HR", "HU", "IE",
            "IS", "IT", "LI", "LT", "LU", "LV", "MC", "MT", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK", "SM");

    /** Above this, EUR payments go to T2 unless the customer asked for instant. */
    static final BigDecimal HIGH_VALUE_EUR = new BigDecimal("1000000.00");

    private SchemeRouter() {
    }

    public static Scheme route(Iban creditor, String currency, BigDecimal amount, boolean instantRequested,
                               boolean urgent) {
        boolean sepaReachable = "EUR".equals(currency) && SEPA.contains(creditor.countryCode());
        if (!sepaReachable) {
            return Scheme.SWIFT_CBPR;
        }
        if (instantRequested) {
            return Scheme.SCT_INST;
        }
        if (urgent || amount.compareTo(HIGH_VALUE_EUR) >= 0) {
            return Scheme.T2;
        }
        return Scheme.SCT;
    }
}
