# disputes-svc

Chargebacks and merchant refunds for DSS26 Bank cards. Back-office analysts
open and work chargeback cases here; the service tracks representment
deadlines, publishes the case lifecycle to Kafka, and closes out merchant
refunds.

Owned by **Cards Servicing** (`@dss26-org/cards-servicing`). Slack
`#cards-servicing`.

## Architecture

```
back-office ──► POST /v1/chargebacks ──► Postgres (chargeback) ──► cards.chargeback.opened.v1
            ──► POST /v1/chargebacks/{id}/resolution ─────────────► cards.chargeback.resolved.v1
                                                                          │
                                       sink-elastic-disputes-search ◄─────┘  (Cards Platform)
                                                  │
                                                  ▼
                        Elasticsearch disputes-search (index template owned here)
                                                  ▲
back-office ──► GET /v1/chargebacks/search ───────┘

cards.refund.requested.v1 ──► RefundRequestListener ──► Postgres (refund) ──► cards.refund.completed.v1
         (group disputes-svc-refunds)
```

- Events are published after the database commit
  (`@TransactionalEventListener(AFTER_COMMIT)`), keyed by chargeback id.
- Network reason codes map to the `reason_category` on the event
  (`ReasonCodes`): Visa by Claims Resolution group, Mastercard code by code.
- Deadlines: 30 days for a Visa dispute response, 45 for a Mastercard second
  presentment. `disputes.chargebacks.due_soon` counts open cases with 5 days
  or less left.

## Events

| Direction | Topic | Group | Schema |
|-----------|-------|-------|--------|
| out | `cards.chargeback.opened.v1` | | `src/main/avro/cards.chargeback.opened.v1.avsc` |
| out | `cards.chargeback.resolved.v1` | | `src/main/avro/cards.chargeback.resolved.v1.avsc` |
| in | `cards.refund.requested.v1` | `disputes-svc-refunds` | `src/main/avro/cards.refund.requested.v1.avsc` |
| out | `cards.refund.completed.v1` | | `src/main/avro/cards.refund.completed.v1.avsc` |

Topics live on `cards-prod-euw1` and are catalogued by Cards Platform. The
producer never auto-registers schemas (`auto.register.schemas=false`).

## Search index

The `sink-elastic-disputes-search` connector (owned by Cards Platform) writes
both chargeback topics to Elasticsearch, one index per topic, document id =
record key. We own what those documents look like once indexed:

- `search/index-template.json` - composable template for `cards.chargeback.*`
  with explicit mappings (`dynamic: false`) and the `disputes-search` alias the
  back-office search reads.
- `search/apply-index-template.sh` - apply it to one environment.

A template only affects new indices. After a mapping change, roll the indices
over in uat first, check the search tab, then prod. Search looks stale? Check
the connector first (Lenses > Connect > `sink-elastic-disputes-search`, and its
DLQ `cards.chargeback.search.v1.dlq`), then the mapping. Connector issues go to
`#cards-platform`.

## Dashboards

- Datadog: [disputes-svc](https://app.datadoghq.eu/dashboard/v2c-8nf-x7k/disputes-svc)
  (cases opened/resolved, due-soon gauge, refund lag, API errors).
- Lag on `disputes-svc-refunds`: Lenses, `cards-prod-euw1`.

## On-call

Tier 1 (representment deadlines are money). PagerDuty service `PSVC8KD`,
escalation policy "Cards Servicing - Primary". Paging monitors: API error rate
above 5% for 10 minutes; `disputes-svc-refunds` lag above 5,000 for 30 minutes.
