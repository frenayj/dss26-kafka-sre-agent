# card-lifecycle-svc

System of record for the state of every DSS26 Bank card: issued, active,
blocked, replaced. Channels, the contact centre and the risk engine change a
card's state through this service, and every change is published as a
`cards.card.*` event.

Owned by **Cards Servicing** (`@dss26-org/cards-servicing`). Slack
`#cards-servicing`.

## Architecture

```
mobile / web BFF, contact centre ──► REST /v1/cards ──► CardService ──► Postgres (card + outbox, one transaction)
                                                              ▲                     │
risk.limit.breached.v1 ──► RiskLimitListener ─────────────────┘                     │ OutboxPublisher (every 200 ms)
        (group card-lifecycle-svc)                                                  ▼
                                    cards.card.issued.v1 / activated.v1 / blocked.v1 / replaced.v1
```

- **State machine** (`card/CardStateMachine.kt`) is the only place that
  decides what is legal. Plastic cards start `ISSUED` and need activation;
  virtual and tokenised cards start `ACTIVE`. Only a customer freeze can be
  lifted; lost, stolen and fraud blocks end in a replacement.
- **Outbox**: events are written in the card's transaction and published in
  id order, keyed by card token, so consumers see one card's events in order.
  Payloads are Avro JSON-encoded in `outbox.payload` (readable in psql).
- **Auto-block**: `EXPOSURE` and `MCC_RESTRICTED` breaches from the risk
  engine block the card (`FRAUD_SUSPECTED`, initiator `SYSTEM`). Velocity
  breaches only alert the cardholder.

## Events

| Direction | Topic | Group | Schema |
|-----------|-------|-------|--------|
| out | `cards.card.issued.v1` | | `src/main/avro/cards.card.issued.v1.avsc` |
| out | `cards.card.activated.v1` | | `src/main/avro/cards.card.activated.v1.avsc` |
| out | `cards.card.blocked.v1` | | `src/main/avro/cards.card.blocked.v1.avsc` |
| out | `cards.card.replaced.v1` | | `src/main/avro/cards.card.replaced.v1.avsc` |
| in | `risk.limit.breached.v1` | `card-lifecycle-svc` | `src/main/avro/risk.limit.breached.v1.avsc` (Risk Platform's schema) |

Known consumers: card fulfilment (plastic mailing), the apps (virtual card
provisioning), aml-transaction-screening (card to customer lookup).

## Dashboards

- Datadog: [card-lifecycle-svc](https://app.datadoghq.eu/dashboard/r8d-3vk-q6p/card-lifecycle-svc)
  (state changes per type, outbox depth and age, auto-blocks).
- Monitor (warn, `#cards-servicing`): oldest unpublished outbox row older than
  60 seconds.

## Runbooks

**Outbox not draining.** Check producer errors in the logs; the publisher
retries the whole batch, so a single bad row blocks the rest. `SELECT id,
event_type, created_at FROM outbox WHERE published_at IS NULL ORDER BY id
LIMIT 10;` shows the head of the queue.

**Card wrongly auto-blocked.** Unblock is not possible for `FRAUD_SUSPECTED`
by design. The contact centre replaces the card; tell `#risk-platform` which
breach caused it.

## On-call

Tier 2. Business hours: Cards Servicing. Out of hours, blocking still works
through the authorisation host's hot-card list (contact centre procedure), so
nobody is paged for this service.
