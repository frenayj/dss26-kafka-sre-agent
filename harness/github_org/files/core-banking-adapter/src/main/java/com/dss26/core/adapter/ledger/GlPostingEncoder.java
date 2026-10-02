package com.dss26.core.adapter.ledger;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.ByteBuffer;
import java.nio.charset.Charset;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

/**
 * Encodes a journal posting into the GLPOST01 copybook layout: EBCDIC
 * (IBM-1047) text fields, space padded, and the amount as packed decimal
 * (COMP-3, PIC S9(13)V99).
 */
public final class GlPostingEncoder {

    public static final int RECORD_LENGTH = 172;
    static final Charset EBCDIC = Charset.forName("IBM1047");
    private static final DateTimeFormatter YYYYMMDD = DateTimeFormatter.BASIC_ISO_DATE;

    private GlPostingEncoder() {
    }

    public static byte[] encode(String journalId, String sourceSystem, String sourceRef, String debitAccount,
                                String creditAccount, BigDecimal amount, String currency, LocalDate valueDate) {
        ByteBuffer buf = ByteBuffer.allocate(RECORD_LENGTH);
        text(buf, journalId, 36);
        text(buf, sourceSystem, 24);
        text(buf, sourceRef, 36);
        text(buf, debitAccount, 20);
        text(buf, creditAccount, 20);
        buf.put(packedDecimal(amount, 13, 2));
        text(buf, currency, 3);
        text(buf, valueDate.format(YYYYMMDD), 8);
        text(buf, "", 17);
        return buf.array();
    }

    static void text(ByteBuffer buf, String value, int length) {
        String v = value == null ? "" : value;
        if (v.length() > length) {
            throw new IllegalArgumentException("'" + v + "' does not fit PIC X(" + length + ")");
        }
        buf.put(String.format("%-" + length + "s", v).getBytes(EBCDIC));
    }

    /** COMP-3: two digits per byte, sign in the last nibble (C positive, D negative). */
    static byte[] packedDecimal(BigDecimal value, int integerDigits, int fractionDigits) {
        BigDecimal scaled = value.setScale(fractionDigits, RoundingMode.UNNECESSARY);
        String digits = scaled.unscaledValue().abs().toString();
        int totalDigits = integerDigits + fractionDigits;
        if (digits.length() > totalDigits) {
            throw new IllegalArgumentException(value + " overflows S9(" + integerDigits + ")V9(" + fractionDigits + ")");
        }
        String padded = "0".repeat(totalDigits - digits.length()) + digits;
        // An odd total keeps the sign in the low nibble of the last byte.
        if (padded.length() % 2 == 0) {
            padded = "0" + padded;
        }
        byte[] out = new byte[(padded.length() + 1) / 2];
        int sign = scaled.signum() < 0 ? 0x0D : 0x0C;
        for (int i = 0; i < out.length; i++) {
            int high = padded.charAt(2 * i) - '0';
            int low = (2 * i + 1 < padded.length()) ? padded.charAt(2 * i + 1) - '0' : sign;
            out[i] = (byte) ((high << 4) | low);
        }
        return out;
    }
}
