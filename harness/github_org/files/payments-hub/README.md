# payments-hub

Outgoing credit transfers for DSS26 Bank customers: SEPA Credit Transfer,
SEPA Instant, urgent EUR payments over T2, and cross-border payments over
SWIFT (CBPR+). The channels submit one JSON payment; the hub verifies the
payee, picks the scheme, screens cross-border payments, builds the ISO 20022
pacs.008 and hands it to the payments gateway for the clearing mechanism.

Owned by **Core Banking** (`@dss26-org/core-banking`), payment rails.
Slack `#payment-rails`.

## Flow

```
channels ──► POST /v1/payments/payee-verification   (VoP, SEPA)
         ──► POST /v1/payments
                 │  SchemeRouter: SCT | SCT_INST | T2 | SWIFT_CBPR
                 │  SWIFT_CBPR: sanctions-screening-svc (CROSS_BORDER_TXN), hold on potential match
                 ▼
            Pacs008Builder (prowide-iso20022) ──► gateway queue payments.out.<scheme> ──► STEP2 / RT1 / TIPS / T2 / SWIFT
```

Debits are reserved in the core ledger through core-banking-adapter before a
payment is accepted from the channel (BFF responsibility).

Scheme details, CSMs and cut-offs: [docs/schemes.md](docs/schemes.md).

## Regulation this code implements

- **Instant Payments Regulation (EU) 2024/886**: Verification of Payee before
  every SEPA transfer, instant priced like standard, no scheme amount cap.
- **SWIFT ISO 20022 migration**: CBPR+ pacs.008 only, MT103 retired.
- **T2** (Eurosystem RTGS) for urgent and high-value EUR.

## Dashboards

Datadog: [payments-hub](https://app.datadoghq.eu/dashboard/q8v-5hd-n3e/payments-hub)
(payments per scheme, SCT Inst end-to-end time, VoP outcomes, held payments).

## On-call

Tier 1. PagerDuty service `PSVC7EQ`, escalation policy "Core Banking -
Primary". Pages: SCT Inst rejects above 1% over 5 minutes, any scheme queue
not drained for 10 minutes, VoP NOT_POSSIBLE above 5%.
