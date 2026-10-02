package com.dss26.cards.disputes.chargeback;

import com.dss26.cards.events.ChargebackCategory;

import java.util.Map;

/**
 * Network reason code -> the bucketed category published on
 * cards.chargeback.opened.v1.
 *
 * Visa uses the Visa Claims Resolution groups (10.x fraud, 11.x authorisation,
 * 12.x processing errors, 13.x consumer disputes). Mastercard codes are mapped
 * one by one; anything we do not know lands in OTHER and shows up on the
 * "unmapped reason codes" panel.
 */
public final class ReasonCodes {

    private static final Map<String, ChargebackCategory> MASTERCARD = Map.of(
            "4837", ChargebackCategory.FRAUD,             // No cardholder authorisation
            "4863", ChargebackCategory.FRAUD,             // Cardholder does not recognise
            "4871", ChargebackCategory.FRAUD,             // Chip liability shift
            "4808", ChargebackCategory.AUTHORISATION,     // Authorisation-related
            "4834", ChargebackCategory.PROCESSING_ERROR,  // Point-of-interaction error
            "4831", ChargebackCategory.PROCESSING_ERROR,  // Transaction amount differs
            "4853", ChargebackCategory.CONSUMER_DISPUTE,  // Cardholder dispute
            "4841", ChargebackCategory.CONSUMER_DISPUTE); // Cancelled recurring

    private ReasonCodes() {
    }

    public static ChargebackCategory categorise(CardNetwork network, String reasonCode) {
        if (reasonCode == null || reasonCode.isBlank()) {
            return ChargebackCategory.OTHER;
        }
        return switch (network) {
            case VISA -> visa(reasonCode.trim());
            case MASTERCARD -> MASTERCARD.getOrDefault(reasonCode.trim(), ChargebackCategory.OTHER);
        };
    }

    private static ChargebackCategory visa(String code) {
        String group = code.contains(".") ? code.substring(0, code.indexOf('.')) : code;
        return switch (group) {
            case "10" -> ChargebackCategory.FRAUD;
            case "11" -> ChargebackCategory.AUTHORISATION;
            case "12" -> ChargebackCategory.PROCESSING_ERROR;
            case "13" -> ChargebackCategory.CONSUMER_DISPUTE;
            default -> ChargebackCategory.OTHER;
        };
    }
}
