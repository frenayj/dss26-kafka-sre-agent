package com.dss26.payments.hub.routing;

import com.dss26.payments.hub.iban.Iban;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

class SchemeRouterTest {

    private static final Iban DE = Iban.parse("DE89370400440532013000");
    private static final Iban GB = Iban.parse("GB29NWBK60161331926819");

    @Test
    void euroToSepaIsSct() {
        assertThat(SchemeRouter.route(DE, "EUR", new BigDecimal("250.00"), false, false)).isEqualTo(Scheme.SCT);
    }

    @Test
    void instantHasNoAmountCapAnyMore() {
        assertThat(SchemeRouter.route(DE, "EUR", new BigDecimal("250000.00"), true, false)).isEqualTo(Scheme.SCT_INST);
    }

    @Test
    void urgentOrHighValueEuroGoesToT2() {
        assertThat(SchemeRouter.route(DE, "EUR", new BigDecimal("50.00"), false, true)).isEqualTo(Scheme.T2);
        assertThat(SchemeRouter.route(DE, "EUR", new BigDecimal("2500000.00"), false, false)).isEqualTo(Scheme.T2);
    }

    @Test
    void nonEuroGoesToSwift() {
        assertThat(SchemeRouter.route(GB, "GBP", new BigDecimal("80.00"), false, false)).isEqualTo(Scheme.SWIFT_CBPR);
    }
}
