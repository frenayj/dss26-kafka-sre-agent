package com.dss26.payments.hub.iban;

import java.math.BigInteger;
import java.util.Locale;
import java.util.Map;

/** ISO 13616 IBAN: country length table and the mod-97 check (ISO 7064). */
public final class Iban {

    private static final Map<String, Integer> LENGTHS = Map.ofEntries(
            Map.entry("AT", 20), Map.entry("BE", 16), Map.entry("CH", 21), Map.entry("DE", 22),
            Map.entry("DK", 18), Map.entry("ES", 24), Map.entry("FI", 18), Map.entry("FR", 27),
            Map.entry("GB", 22), Map.entry("IE", 22), Map.entry("IT", 27), Map.entry("LU", 20),
            Map.entry("NL", 18), Map.entry("NO", 15), Map.entry("PL", 28), Map.entry("PT", 25),
            Map.entry("SE", 24));

    private static final BigInteger NINETY_SEVEN = BigInteger.valueOf(97);

    private final String value;

    private Iban(String value) {
        this.value = value;
    }

    public static Iban parse(String raw) {
        String compact = raw.replace(" ", "").toUpperCase(Locale.ROOT);
        if (!isValid(compact)) {
            throw new IllegalArgumentException("Invalid IBAN");
        }
        return new Iban(compact);
    }

    public static boolean isValid(String compact) {
        if (compact == null || compact.length() < 5 || !compact.matches("[A-Z]{2}[0-9]{2}[A-Z0-9]+")) {
            return false;
        }
        Integer expected = LENGTHS.get(compact.substring(0, 2));
        if (expected != null && expected != compact.length()) {
            return false;
        }
        String rearranged = compact.substring(4) + compact.substring(0, 4);
        StringBuilder digits = new StringBuilder();
        for (char c : rearranged.toCharArray()) {
            digits.append(Character.isDigit(c) ? String.valueOf(c) : String.valueOf(c - 'A' + 10));
        }
        return new BigInteger(digits.toString()).mod(NINETY_SEVEN).intValue() == 1;
    }

    public String countryCode() {
        return value.substring(0, 2);
    }

    @Override
    public String toString() {
        return value;
    }
}
