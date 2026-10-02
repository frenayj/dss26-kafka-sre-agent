package com.dss26.payments.gateway.api;

/**
 * How the card was presented. Fraud decisioning applies different thresholds
 * per channel.
 */
public enum Channel {
    CARD_PRESENT,
    ECOM,
    RECURRING,
    MOTO
}
