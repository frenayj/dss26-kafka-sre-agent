package com.dss26.cards.disputes.chargeback;

import com.dss26.cards.events.ChargebackCategory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.assertj.core.api.Assertions.assertThat;

class ReasonCodesTest {

    @ParameterizedTest
    @CsvSource({
            "VISA, 10.4, FRAUD",
            "VISA, 11.3, AUTHORISATION",
            "VISA, 12.6.1, PROCESSING_ERROR",
            "VISA, 13.1, CONSUMER_DISPUTE",
            "MASTERCARD, 4837, FRAUD",
            "MASTERCARD, 4808, AUTHORISATION",
            "MASTERCARD, 4834, PROCESSING_ERROR",
            "MASTERCARD, 4853, CONSUMER_DISPUTE"
    })
    void mapsKnownCodes(CardNetwork network, String code, ChargebackCategory expected) {
        assertThat(ReasonCodes.categorise(network, code)).isEqualTo(expected);
    }

    @Test
    void unknownCodesAreOther() {
        assertThat(ReasonCodes.categorise(CardNetwork.MASTERCARD, "4999")).isEqualTo(ChargebackCategory.OTHER);
        assertThat(ReasonCodes.categorise(CardNetwork.VISA, "")).isEqualTo(ChargebackCategory.OTHER);
    }
}
