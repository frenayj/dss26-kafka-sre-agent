package com.dss26.payments.hub.routing;

public enum Scheme {
    /** SEPA Credit Transfer, via STEP2 (D+1). */
    SCT,
    /** SEPA Instant Credit Transfer, via RT1 or TIPS (10 seconds). */
    SCT_INST,
    /** T2 RTGS for urgent and high-value EUR payments (ISO 20022 since March 2023). */
    T2,
    /** SWIFT CBPR+ (pacs.008) for non-EUR or non-SEPA destinations. */
    SWIFT_CBPR
}
