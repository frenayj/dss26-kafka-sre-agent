package com.dss26.core.adapter.ledger;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDate;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GlPostingEncoderTest {

    @Test
    void packsPositiveAmounts() {
        // S9(13)V99 COMP-3 = 15 digits + sign = 8 bytes: 000000000098765C
        byte[] packed = GlPostingEncoder.packedDecimal(new BigDecimal("987.65"), 13, 2);
        assertArrayEquals(new byte[]{0x00, 0x00, 0x00, 0x00, 0x00, (byte) 0x98, 0x76, 0x5C}, packed);
    }

    @Test
    void negativeAmountsCarryTheDSign() {
        byte[] packed = GlPostingEncoder.packedDecimal(new BigDecimal("-0.50"), 13, 2);
        assertEquals((byte) 0x0D, (byte) (packed[7] & 0x0F));
    }

    @Test
    void recordHasTheCopybookLength() {
        byte[] record = GlPostingEncoder.encode("6b1f0c4e-1d2a-4e0b-9a77-3c5d8e2f4a01", "clearing-settlement-svc",
                "batch-20260302", "1420-SCHEME-CLEARING", "2310-MERCHANT-PAYABLE", new BigDecimal("15032.10"),
                "EUR", LocalDate.of(2026, 3, 2));
        assertEquals(GlPostingEncoder.RECORD_LENGTH, record.length);
    }

    @Test
    void refusesFieldsThatDoNotFit() {
        assertThrows(IllegalArgumentException.class,
                () -> GlPostingEncoder.packedDecimal(new BigDecimal("99999999999999.99"), 13, 2));
    }
}
