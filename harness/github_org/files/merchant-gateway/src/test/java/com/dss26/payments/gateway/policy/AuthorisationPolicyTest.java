package com.dss26.payments.gateway.policy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import com.dss26.payments.gateway.api.AuthorisationRejectedException;
import com.dss26.payments.gateway.api.AuthorisationRequest;
import com.dss26.payments.gateway.api.Channel;

class AuthorisationPolicyTest {

    private final AuthorisationPolicy policy = new AuthorisationPolicy();

    @Test
    void acceptsAmountsWithinTheCurrencyMinorUnit() {
        assertThatCode(() -> policy.check(request("42.50", "EUR"))).doesNotThrowAnyException();
        assertThatCode(() -> policy.check(request("1500", "JPY"))).doesNotThrowAnyException();
        assertThatCode(() -> policy.check(request("1250.375", "KWD"))).doesNotThrowAnyException();
    }

    @Test
    void trailingZerosDoNotCountAsDecimalPlaces() {
        assertThatCode(() -> policy.check(request("1500.00", "JPY"))).doesNotThrowAnyException();
        assertThatCode(() -> policy.check(request("10.500", "EUR"))).doesNotThrowAnyException();
    }

    @Test
    void rejectsMoreDecimalPlacesThanTheCurrencyAllows() {
        assertThatThrownBy(() -> policy.check(request("1500.5", "JPY")))
                .isInstanceOfSatisfying(AuthorisationRejectedException.class, e -> {
                    assertThat(e.status()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
                    assertThat(e.code()).isEqualTo("invalid_amount_scale");
                });
        assertThatThrownBy(() -> policy.check(request("42.505", "EUR")))
                .isInstanceOf(AuthorisationRejectedException.class);
    }

    private static AuthorisationRequest request(String amount, String currency) {
        return new AuthorisationRequest("mch_lumen_coffee", "tok_4410982", new BigDecimal(amount), currency, "FR",
                List.of(), Channel.ECOM);
    }
}
