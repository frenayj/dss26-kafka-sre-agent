package com.dss26.customer.profile.profile;

import org.junit.jupiter.api.Test;

import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;

class ChangedFieldsTest {

    private static final Profile BEFORE = new Profile("CUST-51207", "Anna", "de Wit", LocalDate.of(1990, 2, 1),
            "NL", "anna@example.org", "+31 6 1200 3400", "Prinsengracht 12, Amsterdam", false, false);

    @Test
    void reportsOnlyWhatChanged() {
        Profile after = new Profile("CUST-51207", "Anna", "de Wit", LocalDate.of(1990, 2, 1),
                "NL", "anna.dewit@example.org", "+31 6 1200 3400", "Keizersgracht 80, Amsterdam", false, true);
        assertThat(ChangedFields.between(BEFORE, after)).containsExactly("email", "address", "marketing_sms");
    }

    @Test
    void identicalProfilesChangeNothing() {
        assertThat(ChangedFields.between(BEFORE, BEFORE)).isEmpty();
    }
}
