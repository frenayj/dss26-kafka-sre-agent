package com.dss26.cards.clearing.fees;

import com.dss26.cards.clearing.fees.InterchangeCalculator.Region;
import com.dss26.cards.events.CardNetwork;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

class InterchangeCalculatorTest {

    private static final BigDecimal HUNDRED = new BigDecimal("100.00");

    @Test
    void consumerDebitInsideTheEeaIsCappedAtTwentyBasisPoints() {
        var fees = InterchangeCalculator.calculate(CardNetwork.VISA, CardProduct.CONSUMER_DEBIT,
                Region.INTRA_EEA, false, HUNDRED);
        assertThat(fees.interchange()).isEqualByComparingTo("0.20");
        assertThat(fees.program()).isEqualTo("EEA-IFR/CONSUMER-DEBIT");
    }

    @Test
    void consumerCreditInsideTheEeaIsCappedAtThirtyBasisPoints() {
        var fees = InterchangeCalculator.calculate(CardNetwork.MASTERCARD, CardProduct.CONSUMER_CREDIT,
                Region.INTRA_EEA, true, HUNDRED);
        assertThat(fees.interchange()).isEqualByComparingTo("0.30");
    }

    @Test
    void interRegionalCardNotPresentCreditUsesTheCommitmentRate() {
        var fees = InterchangeCalculator.calculate(CardNetwork.VISA, CardProduct.CONSUMER_CREDIT,
                Region.INTER_REGIONAL, false, HUNDRED);
        assertThat(fees.interchange()).isEqualByComparingTo("1.50");
        assertThat(fees.program()).isEqualTo("INTER-CNP/CONSUMER-CREDIT");
    }

    @Test
    void totalIsTheSumOfTheParts() {
        var fees = InterchangeCalculator.calculate(CardNetwork.VISA, CardProduct.CONSUMER_DEBIT,
                Region.INTRA_EEA, true, new BigDecimal("250.00"));
        assertThat(fees.total()).isEqualByComparingTo(
                fees.interchange().add(fees.schemeFee()).add(fees.acquirerMarkup()));
    }
}
