package com.dss26.cards.clearing.settlement;

import org.junit.jupiter.api.Test;

import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;

class TargetCalendarTest {

    @Test
    void easterDatesAreRight() {
        assertThat(TargetCalendar.easterSunday(2025)).isEqualTo(LocalDate.of(2025, 4, 20));
        assertThat(TargetCalendar.easterSunday(2026)).isEqualTo(LocalDate.of(2026, 4, 5));
    }

    @Test
    void goodFridayAndEasterMondayAreClosed() {
        assertThat(TargetCalendar.isBusinessDay(LocalDate.of(2026, 4, 3))).isFalse();
        assertThat(TargetCalendar.isBusinessDay(LocalDate.of(2026, 4, 6))).isFalse();
        assertThat(TargetCalendar.isBusinessDay(LocalDate.of(2026, 4, 7))).isTrue();
    }

    @Test
    void labourDayAndChristmasAreClosed() {
        assertThat(TargetCalendar.isBusinessDay(LocalDate.of(2026, 5, 1))).isFalse();
        assertThat(TargetCalendar.isBusinessDay(LocalDate.of(2026, 12, 25))).isFalse();
        assertThat(TargetCalendar.isBusinessDay(LocalDate.of(2026, 12, 28))).isTrue();
    }
}
