package com.dss26.payments.hub.iban;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class IbanTest {

    @Test
    void acceptsValidIbans() {
        assertThat(Iban.isValid("DE89370400440532013000")).isTrue();
        assertThat(Iban.isValid("GB29NWBK60161331926819")).isTrue();
        assertThat(Iban.isValid("NL91ABNA0417164300")).isTrue();
        assertThat(Iban.parse("fr14 2004 1010 0505 0001 3m02 606").countryCode()).isEqualTo("FR");
    }

    @Test
    void rejectsBadCheckDigitsAndLengths() {
        assertThat(Iban.isValid("DE89370400440532013001")).isFalse();
        assertThat(Iban.isValid("NL91ABNA041716430")).isFalse();
        assertThatThrownBy(() -> Iban.parse("not an iban")).isInstanceOf(IllegalArgumentException.class);
    }
}
