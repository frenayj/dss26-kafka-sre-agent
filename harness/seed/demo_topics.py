"""Source of truth for the demo's Kafka catalogue.

Defines every topic the SRE-agent demo expects to see in Lenses HQ: the two
production-flow topics (``cards.authorisation.requested.v1`` and
``cards.ledger.posted.v1``) plus 30 catalogue-only "fake" topics that make
the cluster look like a real global-FSI cards platform.

Three concerns are kept together here on purpose:

* **Topic creation** - ``seed_demo_topics.py`` consumes ``TOPICS`` to know
  which topics to create on the broker, with what partition count.
* **Schema Registry seeding** - same script registers ``avro_schema`` as the
  ``<topic>-value`` subject in the Schema Registry. Topics whose
  ``avro_schema`` is ``None`` are skipped here (they're owned by a producer
  that registers its own schema - the two live topics).
* **HQ catalogue metadata** - ``apply_topic_metadata.py`` loops over
  ``TOPICS`` and PUTs ``description`` + ``tags`` against the HQ proxy API
  for each topic.

No data is produced to the 30 catalogue topics. They exist purely to give the
diagnosis sub-agent a realistic catalogue to navigate and to make demo
screenshots look like production.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# TopicSpec - the row shape consumed by both seeding scripts.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicSpec:
    name: str
    description: str
    tags: tuple[str, ...]
    # None = a producer outside our control creates the topic and registers
    # the value schema. seed_demo_topics.py treats those as no-op.
    avro_schema: dict[str, Any] | None = None
    partitions: int = 3


# ---------------------------------------------------------------------------
# Tag composer - keeps every topic's tag list mechanically consistent.
# ---------------------------------------------------------------------------


def tags_for(
    *,
    domain: str,
    owner: str,
    criticality: str,
    compliance: tuple[str, ...],
    pii: str,
    event_type: str,
    extras: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Build the tag tuple used by every demo topic.

    Order is stable so re-applying via PUT produces the same payload across
    runs (Lenses HQ doesn't reorder, but it makes diffing easier).
    """
    return (
        f"domain:{domain}",
        f"owner:{owner}",
        f"criticality:{criticality}",
        *(f"compliance:{c}" for c in compliance),
        f"pii:{pii}",
        "data-residency:eu",
        f"event-type:{event_type}",
        "schema-version:v1",
        "lifecycle:active",
        *extras,
    )


# ---------------------------------------------------------------------------
# Avro helpers - the 30 schemas all follow the same shape, so we build
# them via these small builders instead of writing 30 record JSONs by hand.
# ---------------------------------------------------------------------------


def record(
    name: str, namespace: str, doc: str, fields: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "type": "record",
        "name": name,
        "namespace": namespace,
        "doc": doc,
        "fields": fields,
    }


def f(name: str, type_: Any, doc: str, default: Any = ...) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "type": type_, "doc": doc}
    if default is not ...:
        out["default"] = default
    return out


def enum(name: str, symbols: list[str]) -> dict[str, Any]:
    return {"type": "enum", "name": name, "symbols": symbols}


TS_MILLIS: dict[str, Any] = {"type": "long", "logicalType": "timestamp-millis"}


# Reusable field templates. Saves repeating the same doc strings 20 times.

def card_token_field() -> dict[str, Any]:
    return f(
        "card_token",
        "string",
        "Tokenised PAN. Never the raw card number. PCI-DSS surrogate.",
    )


def merchant_field() -> dict[str, Any]:
    return f("merchant_id", "string", "Acquirer-issued merchant identifier.")


def amount_field() -> dict[str, Any]:
    return f("amount", "double", "Amount in major units of the transaction currency.")


def currency_field() -> dict[str, Any]:
    return f("currency", "string", "ISO-4217 currency code.", default="USD")


def customer_field() -> dict[str, Any]:
    return f("customer_id", "string", "Internal customer identifier (pseudonymised).")


def auth_ref_field() -> dict[str, Any]:
    return f(
        "auth_id",
        "string",
        "Joins back to cards.authorisation.requested.v1 by auth_id.",
    )


def ts_field(name: str = "ts", doc: str = "Event timestamp, epoch millis.") -> dict[str, Any]:
    return f(name, TS_MILLIS, doc)


# ---------------------------------------------------------------------------
# Common tag presets for the four most-used profiles in the catalogue.
# ---------------------------------------------------------------------------

TAGS_CARDS_T1_AUTH = lambda event_type: tags_for(  # noqa: E731
    domain="cards",
    owner="cards-platform",
    criticality="tier-1",
    compliance=("pci-dss", "sox"),
    pii="tokenised",
    event_type=event_type,
)
TAGS_CARDS_T2 = lambda event_type: tags_for(  # noqa: E731
    domain="cards",
    owner="cards-platform",
    criticality="tier-2",
    compliance=("pci-dss",),
    pii="tokenised",
    event_type=event_type,
)
TAGS_CUSTOMER = lambda event_type: tags_for(  # noqa: E731
    domain="customer",
    owner="customer-platform",
    criticality="tier-2",
    compliance=("gdpr", "psd2"),
    pii="personal",
    event_type=event_type,
)
TAGS_FRAUD_T1 = lambda event_type: tags_for(  # noqa: E731
    domain="fraud",
    owner="risk-platform",
    criticality="tier-1",
    compliance=("pci-dss", "sox"),
    pii="tokenised",
    event_type=event_type,
)
TAGS_FRAUD_T2 = lambda event_type: tags_for(  # noqa: E731
    domain="fraud",
    owner="risk-platform",
    criticality="tier-2",
    compliance=("pci-dss",),
    pii="tokenised",
    event_type=event_type,
)
TAGS_RISK = lambda event_type: tags_for(  # noqa: E731
    domain="risk",
    owner="risk-platform",
    criticality="tier-2",
    compliance=("sox",),
    pii="pseudonymised",
    event_type=event_type,
)
TAGS_AML = lambda event_type: tags_for(  # noqa: E731
    domain="aml",
    owner="compliance-platform",
    criticality="tier-1",
    compliance=("aml-kyc", "sox"),
    pii="personal",
    event_type=event_type,
)
TAGS_SANCTIONS = lambda event_type: tags_for(  # noqa: E731
    domain="sanctions",
    owner="compliance-platform",
    criticality="tier-1",
    compliance=("aml-kyc",),
    pii="personal",
    event_type=event_type,
)
TAGS_KYC = lambda event_type: tags_for(  # noqa: E731
    domain="kyc",
    owner="compliance-platform",
    criticality="tier-1",
    compliance=("aml-kyc", "gdpr"),
    pii="personal",
    event_type=event_type,
)
TAGS_LEDGER = lambda event_type: tags_for(  # noqa: E731
    domain="ledger",
    owner="cards-platform",
    criticality="tier-1",
    compliance=("sox", "pci-dss"),
    pii="tokenised",
    event_type=event_type,
)

CARDS_NS = "com.dss26.cards.events"
CUSTOMER_NS = "com.dss26.customer.events"
FRAUD_NS = "com.dss26.fraud.events"
RISK_NS = "com.dss26.risk.events"
AML_NS = "com.dss26.aml.events"
SANCTIONS_NS = "com.dss26.sanctions.events"
KYC_NS = "com.dss26.kyc.events"
LEDGER_NS = "com.dss26.ledger.events"


# ---------------------------------------------------------------------------
# The two LIVE topics - owned by producers; we don't seed them, but the
# catalogue metadata is applied from here so apply_topic_metadata.py has
# one source of truth.
# ---------------------------------------------------------------------------

LIVE_TOPICS: list[TopicSpec] = [
    TopicSpec(
        name="cards.authorisation.requested.v1",
        description=(
            "Card authorisation request events from the merchant-acquirer "
            "gateway (card-present, e-com, recurring, MOTO). PCI-DSS "
            "tokenised - never raw PAN. Tier-1 critical path; BACKWARD "
            "compatibility. Producer: merchant-gateway (payments-edge). Key "
            "consumers: fraud-decisioning-engine, txn-history-builder, "
            "merchant-analytics-stream. Drives cards.ledger.posted.v1. "
            "Retention 7d. SLO: p99 producer→consumer < 200ms; "
            "deserialisation > 99.9%. Owner: cards-platform "
            "(#cards-platform on Slack)."
        ),
        tags=TAGS_CARDS_T1_AUTH("authorisation"),
        avro_schema=None,
    ),
    TopicSpec(
        name="cards.ledger.posted.v1",
        description=(
            "Ledger posting events emitted by fraud-decisioning-engine after "
            "each scored card authorisation. Sole producer; drives the "
            "General Ledger and cardholder-statements. Upstream: "
            "cards.authorisation.requested.v1 (1:1 by auth_id). BACKWARD "
            "compat for SOX replay. PII tokenised. Retention 30d "
            "(regulatory min). SLO: > 99.95% auth→ledger conversion. A drop "
            "in produce rate while upstream is healthy = decisioning engine "
            "stalled = P1. Owner: cards-platform (#cards-platform)."
        ),
        tags=(*TAGS_CARDS_T1_AUTH("ledger-posting"), "upstream:cards.authorisation.requested.v1"),
        avro_schema=None,
    ),
]


# ---------------------------------------------------------------------------
# The 30 catalogue-only topics - created with a registered Avro schema and
# an HQ description + tag set. Zero data is produced to them. Grouped by
# domain.
# ---------------------------------------------------------------------------

CATALOGUE_TOPICS: list[TopicSpec] = [
    # ---- Authorisation lifecycle (5) ---------------------------------------
    TopicSpec(
        name="cards.authorisation.responded.v1",
        description=(
            "Issuer response to an authorisation request - approve or "
            "decline, with auth code on approval and ISO-8583 response "
            "code on decline. 1:1 with cards.authorisation.requested.v1 by "
            "auth_id. Consumed by acquirer-gateway to settle the network "
            "leg of the auth flow."
        ),
        tags=TAGS_CARDS_T1_AUTH("authorisation-response"),
        avro_schema=record(
            "AuthorisationResponded",
            CARDS_NS,
            "Issuer authorisation response paired 1:1 with the requesting auth.",
            [
                auth_ref_field(),
                f("response_code", "string", "ISO-8583 response code, e.g. 00 (approve), 05 (do not honour)."),
                f("approved", "boolean", "Convenience flag: response_code == 00."),
                f("auth_code", ["null", "string"], "6-digit auth code returned on approve; null on decline.", default=None),
                f("issuer_id", "string", "BIN-resolved issuer identifier."),
                ts_field(),
            ],
        ),
    ),
    TopicSpec(
        name="cards.authorisation.declined.v1",
        description=(
            "Declined auths broken out as a first-class stream - used by "
            "fraud-analytics for decline-rate dashboards and by the "
            "cardholder-notification service to push real-time decline "
            "alerts. Sourced from cards.authorisation.responded.v1 where "
            "approved=false."
        ),
        tags=TAGS_CARDS_T1_AUTH("authorisation-declined"),
        avro_schema=record(
            "AuthorisationDeclined",
            CARDS_NS,
            "Declined authorisation - fan-out of cards.authorisation.responded.v1 where approved=false.",
            [
                auth_ref_field(),
                card_token_field(),
                merchant_field(),
                amount_field(),
                currency_field(),
                f("response_code", "string", "ISO-8583 response code that caused the decline."),
                f("decline_reason", enum("DeclineReason", [
                    "INSUFFICIENT_FUNDS", "DO_NOT_HONOUR", "EXPIRED_CARD",
                    "FRAUD_SUSPECTED", "LOST_OR_STOLEN", "ISSUER_UNAVAILABLE",
                    "RESTRICTED_CARD", "OTHER",
                ]), "Bucketed decline reason for analytics."),
                ts_field(),
            ],
        ),
    ),
    TopicSpec(
        name="cards.authorisation.reversed.v1",
        description=(
            "Auth reversal events - either acquirer-initiated (timeout, "
            "duplicate) or issuer-initiated (clearing didn't arrive in "
            "time). Frees the held funds and unwinds risk. Tier-1 because "
            "missed reversals create real customer impact."
        ),
        tags=TAGS_CARDS_T1_AUTH("authorisation-reversal"),
        avro_schema=record(
            "AuthorisationReversed",
            CARDS_NS,
            "Reversal of a previously-approved authorisation.",
            [
                auth_ref_field(),
                f("reversal_id", "string", "Globally unique reversal ID."),
                f("reversed_amount", "double", "Amount being reversed; may be partial (<= original auth)."),
                currency_field(),
                f("initiator", enum("ReversalInitiator", ["ACQUIRER", "ISSUER", "MERCHANT"]),
                  "Which side initiated the reversal."),
                f("reason", "string", "Human-readable reason code carried from the network."),
                ts_field("reversed_at", "Reversal timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.authorisation.captured.v1",
        description=(
            "Capture of a delayed-capture auth (typical for hospitality / "
            "car-hire / e-com). Triggers downstream clearing. Joins back to "
            "the original auth_id."
        ),
        tags=TAGS_CARDS_T1_AUTH("authorisation-capture"),
        avro_schema=record(
            "AuthorisationCaptured",
            CARDS_NS,
            "Capture event against a delayed-capture authorisation.",
            [
                auth_ref_field(),
                f("capture_id", "string", "Globally unique capture ID."),
                f("captured_amount", "double", "Captured amount; <= original auth (partial captures allowed)."),
                currency_field(),
                f("capture_sequence", "int", "1-based sequence number when multiple captures hit the same auth."),
                f("final_capture", "boolean", "True when no further captures will follow."),
                ts_field("captured_at", "Capture timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.authorisation.expired.v1",
        description=(
            "Auth holds that aged out before being captured. Used by the "
            "ledger to release held funds and by merchant analytics to "
            "track unrealised auths. Roughly 1–3% of approved auths."
        ),
        tags=TAGS_CARDS_T2("authorisation-expired"),
        avro_schema=record(
            "AuthorisationExpired",
            CARDS_NS,
            "Auth hold expired without being captured.",
            [
                auth_ref_field(),
                f("original_amount", "double", "Authorised amount that has now been released."),
                currency_field(),
                f("hold_duration_hours", "int", "Hours between auth approval and expiry."),
                ts_field("expired_at", "Expiry timestamp, epoch millis."),
            ],
        ),
    ),

    # ---- Clearing & settlement (4) -----------------------------------------
    TopicSpec(
        name="cards.clearing.received.v1",
        description=(
            "Inbound clearing records from the card networks (Visa Base II, "
            "Mastercard IPM). One record per presentment. Acks the network "
            "leg of the transaction; precedes settlement."
        ),
        tags=TAGS_CARDS_T1_AUTH("clearing-receipt"),
        avro_schema=record(
            "ClearingReceived",
            CARDS_NS,
            "Inbound clearing presentment from the card network.",
            [
                f("clearing_id", "string", "Globally unique clearing record ID."),
                f("network", enum("CardNetwork", ["VISA", "MASTERCARD", "AMEX", "DISCOVER", "JCB"]),
                  "Card network this record came from."),
                f("network_reference", "string", "Network's own reference (e.g. Visa ARN)."),
                card_token_field(),
                merchant_field(),
                amount_field(),
                currency_field(),
                ts_field("received_at", "When the clearing record was ingested."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.clearing.matched.v1",
        description=(
            "Clearing records matched back to their originating auth. "
            "Unmatched clearings (no auth or auth amount mismatch) get "
            "routed to a separate exceptions topic upstream of the GL."
        ),
        tags=TAGS_CARDS_T1_AUTH("clearing-match"),
        avro_schema=record(
            "ClearingMatched",
            CARDS_NS,
            "Successful match between a clearing record and its originating auth.",
            [
                f("clearing_id", "string", "ID of the cleared record."),
                auth_ref_field(),
                f("auth_amount", "double", "Original auth amount."),
                f("clearing_amount", "double", "Cleared amount."),
                f("amount_delta", "double", "clearing_amount - auth_amount (0.0 for exact matches)."),
                f("match_confidence", "double", "0.0..1.0 confidence score from the matcher."),
                ts_field("matched_at", "Match timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.settlement.batch.posted.v1",
        description=(
            "Daily merchant settlement batch summaries. One record per "
            "merchant per settlement window. Drives merchant funding and "
            "the GL's revenue posting; SOX-relevant."
        ),
        tags=TAGS_CARDS_T1_AUTH("settlement-batch"),
        avro_schema=record(
            "SettlementBatchPosted",
            CARDS_NS,
            "Daily settlement batch summary per merchant.",
            [
                f("batch_id", "string", "Globally unique settlement batch ID."),
                merchant_field(),
                f("settlement_date", "string", "ISO-8601 date of the settlement window (YYYY-MM-DD)."),
                f("gross_amount", "double", "Sum of cleared amounts in the batch."),
                f("fees_amount", "double", "Total interchange + scheme fees deducted."),
                f("net_amount", "double", "gross_amount - fees_amount, paid to the merchant."),
                currency_field(),
                f("transaction_count", "int", "Number of cleared transactions in the batch."),
                ts_field("posted_at", "When the batch was posted to settlement."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.interchange.fee.calculated.v1",
        description=(
            "Per-transaction interchange + scheme fee breakdown. Computed "
            "from network rates against the cleared amount. Feeds revenue "
            "analytics and the GL fee accruals."
        ),
        tags=TAGS_CARDS_T1_AUTH("interchange-fee"),
        avro_schema=record(
            "InterchangeFeeCalculated",
            CARDS_NS,
            "Interchange + scheme fee breakdown for a cleared transaction.",
            [
                f("clearing_id", "string", "Source clearing record."),
                auth_ref_field(),
                f("interchange_fee", "double", "Network interchange fee (issuer leg)."),
                f("scheme_fee", "double", "Network scheme fee (Visa/MC processing)."),
                f("acquirer_markup", "double", "Acquirer-side markup."),
                f("total_fee", "double", "Sum of all fee components."),
                currency_field(),
                f("interchange_program", "string", "Network program code, e.g. CPS/RETAIL, EIRF."),
                ts_field("calculated_at", "Fee-calc timestamp, epoch millis."),
            ],
        ),
    ),

    # ---- Disputes & refunds (4) --------------------------------------------
    TopicSpec(
        name="cards.chargeback.opened.v1",
        description=(
            "Cardholder-initiated chargeback raised against a cleared "
            "transaction. Network reason codes (e.g. Visa 13.1, MC 4853). "
            "Tier-1: tight SLAs to represent before deadlines."
        ),
        tags=TAGS_CARDS_T1_AUTH("chargeback-opened"),
        avro_schema=record(
            "ChargebackOpened",
            CARDS_NS,
            "New chargeback case raised against a previously cleared transaction.",
            [
                f("chargeback_id", "string", "Globally unique chargeback case ID."),
                auth_ref_field(),
                merchant_field(),
                f("disputed_amount", "double", "Amount being disputed; may be partial."),
                currency_field(),
                f("reason_code", "string", "Network reason code (e.g. Visa 13.1)."),
                f("reason_category", enum("ChargebackCategory", [
                    "FRAUD", "AUTHORISATION", "PROCESSING_ERROR",
                    "CONSUMER_DISPUTE", "OTHER",
                ]), "Bucketed category from the network reason code."),
                ts_field("opened_at", "When the chargeback was opened by the issuer."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.chargeback.resolved.v1",
        description=(
            "Final outcome of a chargeback case: merchant won "
            "(representment succeeded), lost (issuer upheld), or "
            "second-presentment / pre-arbitration escalated. Feeds "
            "merchant-risk scoring and the GL writeback."
        ),
        tags=TAGS_CARDS_T1_AUTH("chargeback-resolved"),
        avro_schema=record(
            "ChargebackResolved",
            CARDS_NS,
            "Final disposition of a chargeback case.",
            [
                f("chargeback_id", "string", "Chargeback case being resolved."),
                f("outcome", enum("ChargebackOutcome", [
                    "MERCHANT_WON", "MERCHANT_LOST", "PRE_ARBITRATION",
                    "ARBITRATION", "WITHDRAWN",
                ]), "Final disposition."),
                f("recovered_amount", "double", "Amount recovered by the merchant; 0.0 on loss."),
                currency_field(),
                f("resolution_days", "int", "Calendar days from open to resolve."),
                ts_field("resolved_at", "Resolution timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.refund.requested.v1",
        description=(
            "Merchant-initiated refund against a previously cleared "
            "auth. Distinct from a chargeback: voluntary from the "
            "merchant. Tier-1 because customers care."
        ),
        tags=TAGS_CARDS_T1_AUTH("refund-requested"),
        avro_schema=record(
            "RefundRequested",
            CARDS_NS,
            "Merchant-initiated refund request against a previously cleared auth.",
            [
                f("refund_id", "string", "Globally unique refund ID."),
                auth_ref_field(),
                card_token_field(),
                amount_field(),
                currency_field(),
                merchant_field(),
                f("reason_code", enum("RefundReason", [
                    "CUSTOMER_REQUEST", "RETURN", "GOODWILL", "DUPLICATE",
                    "PRICE_ADJUSTMENT", "SERVICE_NOT_RENDERED",
                ]), "Why the merchant is refunding."),
                ts_field("requested_at", "Refund request timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.refund.completed.v1",
        description=(
            "Refund fully posted back to the cardholder. Closes out the "
            "refund lifecycle started in cards.refund.requested.v1."
        ),
        tags=TAGS_CARDS_T1_AUTH("refund-completed"),
        avro_schema=record(
            "RefundCompleted",
            CARDS_NS,
            "Refund fully posted to the cardholder.",
            [
                f("refund_id", "string", "Refund being completed."),
                f("completed_amount", "double", "Amount actually returned (may differ from request)."),
                currency_field(),
                f("settlement_batch_id", ["null", "string"],
                  "Settlement batch carrying the refund; null until the next cycle.",
                  default=None),
                ts_field("completed_at", "Completion timestamp, epoch millis."),
            ],
        ),
    ),

    # ---- Card lifecycle (5) ------------------------------------------------
    TopicSpec(
        name="cards.card.issued.v1",
        description=(
            "A new physical or virtual card has been issued. Feeds the "
            "fulfilment service for plastic-card mailing and the "
            "cardholder-app for virtual-card provisioning."
        ),
        tags=TAGS_CARDS_T2("card-issued"),
        avro_schema=record(
            "CardIssued",
            CARDS_NS,
            "New card issued - physical or virtual.",
            [
                card_token_field(),
                customer_field(),
                f("product_code", "string", "Card product code (e.g. PLATINUM_CREDIT, DEBIT_BASIC)."),
                f("form_factor", enum("CardFormFactor", ["PHYSICAL", "VIRTUAL", "TOKENISED"]),
                  "Plastic, virtual-only, or network-token-only."),
                f("bin", "string", "First 6 of the PAN - the issuer's BIN."),
                f("expiry_yyyymm", "string", "Card expiry as YYYYMM."),
                ts_field("issued_at", "Issuance timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.card.activated.v1",
        description=(
            "Cardholder has activated a newly-issued card (call-in, app, "
            "or first-use). Until activation the card is in ISSUED state "
            "and auths will decline."
        ),
        tags=TAGS_CARDS_T2("card-activated"),
        avro_schema=record(
            "CardActivated",
            CARDS_NS,
            "Card activation by the cardholder.",
            [
                card_token_field(),
                customer_field(),
                f("activation_channel", enum("ActivationChannel", [
                    "APP", "WEB", "IVR", "FIRST_USE_AT_TERMINAL",
                ]), "How the cardholder activated."),
                ts_field("activated_at", "Activation timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.card.blocked.v1",
        description=(
            "Card-block event: cardholder-reported lost/stolen, "
            "issuer-side fraud lock, or compliance-triggered freeze. "
            "Causes all subsequent auths to decline until unblocked or "
            "replaced."
        ),
        tags=TAGS_CARDS_T2("card-blocked"),
        avro_schema=record(
            "CardBlocked",
            CARDS_NS,
            "Card placed in BLOCKED state.",
            [
                card_token_field(),
                customer_field(),
                f("block_reason", enum("BlockReason", [
                    "LOST", "STOLEN", "FRAUD_SUSPECTED", "CUSTOMER_REQUEST",
                    "COMPLIANCE_HOLD", "EXPIRED",
                ]), "Why the card was blocked."),
                f("initiator", enum("BlockInitiator", ["CUSTOMER", "ISSUER", "COMPLIANCE", "SYSTEM"]),
                  "Who triggered the block."),
                ts_field("blocked_at", "Block timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.card.replaced.v1",
        description=(
            "A card has been reissued. Links the old token to its "
            "replacement so downstream systems can re-attach mandates, "
            "recurring auths, and stored credentials."
        ),
        tags=TAGS_CARDS_T2("card-replaced"),
        avro_schema=record(
            "CardReplaced",
            CARDS_NS,
            "Card reissue - old card replaced by a new token.",
            [
                f("old_card_token", "string", "Tokenised PAN of the old card; now BLOCKED."),
                f("new_card_token", "string", "Tokenised PAN of the replacement card."),
                customer_field(),
                f("replacement_reason", enum("ReplacementReason", [
                    "LOST", "STOLEN", "COMPROMISED", "EXPIRED",
                    "DAMAGED", "CUSTOMER_REQUEST",
                ]), "Why the card was replaced."),
                ts_field("replaced_at", "Replacement timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="cards.statement.generated.v1",
        description=(
            "Monthly cardholder statement has been generated and is "
            "available in the app + ready for postal print. Feeds the "
            "notifications service and the document-archive pipeline."
        ),
        tags=tags_for(
            domain="cards",
            owner="cards-platform",
            criticality="tier-3",
            compliance=("gdpr",),
            pii="personal",
            event_type="statement-generated",
        ),
        avro_schema=record(
            "StatementGenerated",
            CARDS_NS,
            "Monthly statement generated for a card.",
            [
                f("statement_id", "string", "Globally unique statement ID."),
                customer_field(),
                card_token_field(),
                f("statement_period", "string", "Statement period (YYYY-MM)."),
                f("closing_balance", "double", "Closing balance for the period, major units."),
                currency_field(),
                f("transaction_count", "int", "Number of transactions on the statement."),
                ts_field("generated_at", "Statement generation timestamp."),
            ],
        ),
    ),

    # ---- Customer / account (3) --------------------------------------------
    TopicSpec(
        name="customer.account.opened.v1",
        description=(
            "New customer account has been onboarded. Emitted after KYC "
            "passes and the customer record is created. Drives "
            "downstream provisioning (card issuance, app login, etc)."
        ),
        tags=TAGS_CUSTOMER("account-opened"),
        avro_schema=record(
            "AccountOpened",
            CUSTOMER_NS,
            "New customer account onboarded.",
            [
                customer_field(),
                f("account_number", "string", "Internal account number (pseudonymised)."),
                f("product_code", "string", "Account product, e.g. CURRENT_GBP, SAVINGS_EUR."),
                f("kyc_reference", "string", "Reference to the KYC case that approved this open."),
                f("opening_balance", "double", "Initial balance at open, usually 0.0."),
                currency_field(),
                ts_field("opened_at", "Account-open timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="customer.profile.updated.v1",
        description=(
            "Customer profile changes: address, phone, email, marketing "
            "preferences. GDPR-relevant; consumed by the audit log and "
            "the contact-data master."
        ),
        tags=TAGS_CUSTOMER("profile-updated"),
        avro_schema=record(
            "ProfileUpdated",
            CUSTOMER_NS,
            "One or more customer-profile fields changed.",
            [
                customer_field(),
                f("changed_fields", {"type": "array", "items": "string"},
                  "Field names that changed in this update."),
                f("changed_by", enum("ChangedBy", ["CUSTOMER", "AGENT", "SYSTEM"]),
                  "Who initiated the change."),
                f("agent_id", ["null", "string"], "ID of the agent if changed_by=AGENT.", default=None),
                ts_field("changed_at", "Change timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="customer.consent.granted.v1",
        description=(
            "Customer-granted consent events: PSD2 open-banking access, "
            "marketing opt-in, data-sharing with third parties. Required "
            "evidence for PSD2/GDPR audits; ledgered."
        ),
        tags=TAGS_CUSTOMER("consent-granted"),
        avro_schema=record(
            "ConsentGranted",
            CUSTOMER_NS,
            "Customer granted a specific consent.",
            [
                customer_field(),
                f("consent_id", "string", "Globally unique consent record ID."),
                f("consent_type", enum("ConsentType", [
                    "PSD2_AISP", "PSD2_PISP", "MARKETING_EMAIL",
                    "MARKETING_SMS", "DATA_SHARING_3P", "TELEMETRY",
                ]), "What consent is being granted."),
                f("scope", "string", "Free-form scope details (TPP name, third-party name, etc)."),
                f("expires_at", ["null", TS_MILLIS],
                  "Expiry timestamp; null for perpetual consents.", default=None),
                ts_field("granted_at", "Grant timestamp, epoch millis."),
            ],
        ),
    ),

    # ---- Fraud & risk (4) --------------------------------------------------
    TopicSpec(
        name="fraud.score.computed.v1",
        description=(
            "Real-time fraud score computed per authorisation by the "
            "fraud-decisioning engine. 1:1 with auth. Feeds the "
            "auth-response decision and the fraud-case manager."
        ),
        tags=TAGS_FRAUD_T1("fraud-score"),
        avro_schema=record(
            "FraudScoreComputed",
            FRAUD_NS,
            "Per-auth fraud score from the decisioning engine.",
            [
                auth_ref_field(),
                f("score", "double", "0.0 (low risk) to 1.0 (high risk)."),
                f("decision", enum("FraudDecision", ["APPROVE", "REVIEW", "DECLINE"]),
                  "Recommended action from the model."),
                f("model_version", "string", "Identifier of the scoring model that produced this score."),
                f("rule_matches", {"type": "array", "items": "string"},
                  "Names of rules that fired during scoring.", default=[]),
                ts_field("scored_at", "Scoring timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="fraud.case.opened.v1",
        description=(
            "Manual fraud-investigation case opened. Triggered by "
            "score>=REVIEW threshold or cardholder report. Assigned to a "
            "fraud analyst."
        ),
        tags=TAGS_FRAUD_T2("fraud-case-opened"),
        avro_schema=record(
            "FraudCaseOpened",
            FRAUD_NS,
            "New manual investigation case opened.",
            [
                f("case_id", "string", "Globally unique case ID."),
                customer_field(),
                card_token_field(),
                f("trigger", enum("CaseTrigger", [
                    "MODEL_SCORE", "CARDHOLDER_REPORT", "MERCHANT_REPORT",
                    "NETWORK_ALERT", "RULE",
                ]), "What opened the case."),
                f("triggering_auth_id", ["null", "string"],
                  "Auth that triggered the case, if applicable.", default=None),
                f("priority", enum("CasePriority", ["P1", "P2", "P3", "P4"]),
                  "Initial priority; may be re-graded by the analyst."),
                ts_field("opened_at", "Case-open timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="fraud.case.resolved.v1",
        description=(
            "Fraud-case resolution. Closes out a case opened in "
            "fraud.case.opened.v1 with a final disposition and any "
            "remediation actions taken."
        ),
        tags=TAGS_FRAUD_T2("fraud-case-resolved"),
        avro_schema=record(
            "FraudCaseResolved",
            FRAUD_NS,
            "Final disposition of a fraud investigation case.",
            [
                f("case_id", "string", "Case being resolved."),
                f("outcome", enum("CaseOutcome", [
                    "CONFIRMED_FRAUD", "FALSE_POSITIVE", "INCONCLUSIVE",
                    "REFERRED_LAW_ENFORCEMENT",
                ]), "Analyst's final disposition."),
                f("actions_taken", {"type": "array", "items": "string"},
                  "Remediations applied (e.g. CARD_BLOCKED, REFUND_ISSUED).", default=[]),
                f("loss_amount", "double", "Net loss in the case currency; 0.0 if recovered."),
                currency_field(),
                ts_field("resolved_at", "Resolution timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="risk.limit.breached.v1",
        description=(
            "Velocity / exposure / spend-limit breach detected by the "
            "risk-engine. Feeds the cardholder-alerts service and may "
            "auto-trigger a card-block."
        ),
        tags=TAGS_RISK("risk-limit-breach"),
        avro_schema=record(
            "RiskLimitBreached",
            RISK_NS,
            "A risk limit (velocity, exposure, etc) was breached.",
            [
                customer_field(),
                card_token_field(),
                f("limit_type", enum("LimitType", [
                    "DAILY_VELOCITY", "WEEKLY_VELOCITY", "SINGLE_TXN",
                    "CASH_ADVANCE", "EXPOSURE", "MCC_RESTRICTED",
                ]), "Which limit was breached."),
                f("limit_value", "double", "The limit threshold that was crossed."),
                f("observed_value", "double", "The actual value that breached the limit."),
                currency_field(),
                ts_field("detected_at", "Detection timestamp, epoch millis."),
            ],
        ),
    ),

    # ---- AML / sanctions / KYC (4) -----------------------------------------
    TopicSpec(
        name="aml.transaction.screened.v1",
        description=(
            "AML transaction-monitoring screening result. Every "
            "transaction over the screening threshold lands here. Most "
            "are CLEAR; the rest spawn aml.alert.raised.v1."
        ),
        tags=TAGS_AML("aml-screening"),
        avro_schema=record(
            "TransactionScreened",
            AML_NS,
            "AML transaction-monitoring screening outcome.",
            [
                f("screening_id", "string", "Globally unique screening ID."),
                auth_ref_field(),
                customer_field(),
                f("outcome", enum("AmlOutcome", ["CLEAR", "FLAGGED", "ALERTED"]),
                  "Screening verdict."),
                f("rules_fired", {"type": "array", "items": "string"},
                  "Names of rules that fired during screening.", default=[]),
                f("typology", ["null", "string"],
                  "Suspected typology if flagged (e.g. STRUCTURING, RAPID_MOVEMENT).",
                  default=None),
                ts_field("screened_at", "Screening timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="aml.alert.raised.v1",
        description=(
            "AML alert opened from a flagged screening. Routed to the "
            "compliance team's case-management system; may escalate to "
            "an SAR / STR filing."
        ),
        tags=TAGS_AML("aml-alert"),
        avro_schema=record(
            "AmlAlertRaised",
            AML_NS,
            "AML alert opened from a flagged screening result.",
            [
                f("alert_id", "string", "Globally unique alert ID."),
                f("screening_id", "string", "Source screening (joins to aml.transaction.screened.v1)."),
                customer_field(),
                f("typology", "string", "Suspected typology, e.g. STRUCTURING, LAYERING."),
                f("severity", enum("AlertSeverity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
                  "Initial severity."),
                f("assigned_team", "string", "Compliance team queue the alert is routed to."),
                ts_field("raised_at", "Alert-raised timestamp, epoch millis."),
            ],
        ),
    ),
    TopicSpec(
        name="sanctions.screening.completed.v1",
        description=(
            "Sanctions-list screening outcome (OFAC, UN, EU, UK HMT). "
            "Run on every new account open and on every cross-border "
            "transaction over the threshold."
        ),
        tags=TAGS_SANCTIONS("sanctions-screening"),
        avro_schema=record(
            "SanctionsScreeningCompleted",
            SANCTIONS_NS,
            "Sanctions-list screening result.",
            [
                f("screening_id", "string", "Globally unique sanctions-screening ID."),
                customer_field(),
                f("trigger", enum("SanctionsTrigger", [
                    "ACCOUNT_OPEN", "PERIODIC_REFRESH", "CROSS_BORDER_TXN",
                    "BENEFICIARY_ADDED",
                ]), "What kicked off the screening."),
                f("lists_checked", {"type": "array", "items": "string"},
                  "Sanctions lists screened against (OFAC_SDN, UN_CONSOLIDATED, EU, UK_HMT)."),
                f("outcome", enum("SanctionsOutcome", [
                    "NO_HIT", "POTENTIAL_MATCH", "CONFIRMED_MATCH", "FALSE_POSITIVE",
                ]), "Screening verdict."),
                f("match_score", "double", "Highest fuzzy-match score in this run, 0.0..1.0."),
                ts_field("completed_at", "Screening completion timestamp."),
            ],
        ),
    ),
    TopicSpec(
        name="kyc.verification.completed.v1",
        description=(
            "KYC / CDD verification completed for a customer. Carries "
            "the outcome, the method used, and the expiry of the "
            "verification (for periodic refresh)."
        ),
        tags=TAGS_KYC("kyc-verification"),
        avro_schema=record(
            "KycVerificationCompleted",
            KYC_NS,
            "KYC verification outcome for a customer.",
            [
                customer_field(),
                f("kyc_reference", "string", "Globally unique KYC case reference."),
                f("method", enum("KycMethod", [
                    "DOCUMENT_PHOTO", "VIDEO_CALL", "BANK_ACCOUNT_VERIFICATION",
                    "ELECTRONIC_ID", "IN_BRANCH",
                ]), "How identity was verified."),
                f("outcome", enum("KycOutcome", [
                    "PASS", "FAIL", "MANUAL_REVIEW", "EXPIRED",
                ]), "Verification outcome."),
                f("risk_rating", enum("CustomerRiskRating", ["LOW", "MEDIUM", "HIGH"]),
                  "Resulting customer-risk rating."),
                f("expires_at", TS_MILLIS,
                  "When this verification expires and a refresh is due."),
                ts_field("verified_at", "Verification timestamp, epoch millis."),
            ],
        ),
    ),

    # ---- Ledger (1) --------------------------------------------------------
    TopicSpec(
        name="ledger.journal.posted.v1",
        description=(
            "Generic ledger journal entry posted. Double-entry rows from "
            "cards-platform, settlement, fees, refunds, and chargebacks "
            "all land here. SOX-relevant; immutable replay source."
        ),
        tags=TAGS_LEDGER("ledger-journal"),
        avro_schema=record(
            "JournalPosted",
            LEDGER_NS,
            "Double-entry journal posting in the General Ledger.",
            [
                f("journal_id", "string", "Globally unique journal entry ID."),
                f("source_system", "string", "Originating system (e.g. cards-platform, fees-engine)."),
                f("source_reference", "string", "Source-system reference (e.g. settlement_batch_id)."),
                f("debit_account", "string", "GL account code being debited."),
                f("credit_account", "string", "GL account code being credited."),
                amount_field(),
                currency_field(),
                f("value_date", "string", "Value date in ISO-8601 (YYYY-MM-DD)."),
                ts_field("posted_at", "Posting timestamp, epoch millis."),
            ],
        ),
    ),
]


# ---------------------------------------------------------------------------
# Combined list - what apply_topic_metadata.py iterates over. The order
# matters only for log output; HQ doesn't care.
# ---------------------------------------------------------------------------

TOPICS: list[TopicSpec] = [*LIVE_TOPICS, *CATALOGUE_TOPICS]


def topics_to_seed() -> list[TopicSpec]:
    """Return only the topics this codebase is responsible for creating.

    The two live topics are created by their producers - we don't seed them.
    """
    return [t for t in TOPICS if t.avro_schema is not None]


# Sanity check - fail loudly at import time if the count drifts.
assert len(CATALOGUE_TOPICS) == 30, f"expected 30 catalogue topics, got {len(CATALOGUE_TOPICS)}"


if __name__ == "__main__":
    # Tiny self-printout - handy for quickly eyeballing the catalogue.
    print(f"Live topics: {len(LIVE_TOPICS)}")
    print(f"Catalogue topics: {len(CATALOGUE_TOPICS)}")
    print(f"Total in catalogue: {len(TOPICS)}")
    print()
    for t in TOPICS:
        marker = " (live)" if t.avro_schema is None else ""
        print(f"  {t.name}{marker}")
