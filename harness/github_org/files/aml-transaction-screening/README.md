# aml-transaction-screening

Real-time anti-money-laundering screening of cleared card transactions for
DSS26 Bank. Every presentment that clears is joined with its authorisation
and its cardholder, screened against the typology rules, and recorded on
`aml.transaction.screened.v1`; anything that needs a human becomes an
`aml.alert.raised.v1` for the Financial Intelligence Unit (FIU).

Owned by **Compliance Platform** (`@dss26-org/compliance-platform`).
Slack `#compliance-platform`; compliance questions `#compliance-cards`.

## Architecture

Kafka Streams (Scala), application.id `aml-transaction-screening`.

```
cards.clearing.received.v1 ─┐ join on clearing_id (3 days)
cards.clearing.matched.v1  ─┘          │
                                       ▼ left join card_token (GlobalKTable)
cards.card.issued.v1 ─────────────────►│
                                       ▼ re-key by customer_id
                              Rules.screen ──► aml.transaction.screened.v1
                                       │   └─► aml.alert.raised.v1 (ALERTED)
                                       └─ structuring band, 24h window per customer ──► aml.alert.raised.v1
```

- Rules and thresholds: [docs/typologies.md](docs/typologies.md).
- EUR equivalents use the ECB reference rates in `application.conf`.
- **Nothing is skipped.** The deserialisation handler is
  `LogAndFailExceptionHandler`: a record we cannot read stops the application
  and pages. A gap in screening is a regulatory breach; a stopped screener is
  an incident we can recover from.

## Events

| Direction | Topic | Notes |
|-----------|-------|-------|
| in | `cards.clearing.received.v1` | Clearing & Settlement |
| in | `cards.clearing.matched.v1` | Clearing & Settlement |
| in | `cards.card.issued.v1` | Cards Servicing, read as a global table |
| out | `aml.transaction.screened.v1` | every cleared transaction |
| out | `aml.alert.raised.v1` | routed to the FIU case management queue |

## Runbook: screening stopped

1. Lenses: is lag growing on `aml-transaction-screening` for one input topic
   or both? Look at the stream thread's last exception in the logs.
2. Deserialisation error on a clearing topic: an upstream schema changed.
   Talk to `#clearing-settlement` first; do **not** skip offsets. This is what
   happened in INC-2024-09-12-003.
3. Once the cause is fixed, restart. Screening catches up from the committed
   offsets; tell the FIU how long the gap was (`#compliance-cards`).

## Dashboards

- Datadog: [aml-transaction-screening](https://app.datadoghq.eu/dashboard/c9w-4ry-t2n/aml-transaction-screening)
  (screened/s, alerts per typology, lag, stream thread state).

## On-call

Tier 1. PagerDuty service `PSVC6RT`, escalation policy "Compliance Platform -
Primary". Pages on: any stream thread DEAD, lag above 100,000, no screening
output for 15 minutes during business hours.
