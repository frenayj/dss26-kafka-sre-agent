package com.dss26.payments.gateway.policy;

import java.util.Currency;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import com.dss26.payments.gateway.api.AuthorisationRejectedException;
import com.dss26.payments.gateway.api.AuthorisationRequest;

/**
 * Business rules a request must pass before it is published, beyond what bean
 * validation can express.
 */
@Component
public class AuthorisationPolicy {

    /**
     * Rejects amounts with more decimal places than the currency's minor unit
     * (JPY 0, EUR 2, KWD 3). Downstream systems settle in minor units, so an
     * over-precise amount must be refused at the edge rather than rounded later.
     */
    public void check(AuthorisationRequest request) {
        Currency currency = Currency.getInstance(request.currency());
        int minorDigits = Math.max(currency.getDefaultFractionDigits(), 0);
        if (request.amount().stripTrailingZeros().scale() > minorDigits) {
            throw new AuthorisationRejectedException(HttpStatus.UNPROCESSABLE_ENTITY, "invalid_amount_scale",
                    "%s allows %d decimal places, got %s".formatted(
                            currency.getCurrencyCode(), minorDigits, request.amount().toPlainString()));
        }
    }
}
