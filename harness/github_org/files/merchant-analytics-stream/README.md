# merchant-analytics-stream

Near-real-time merchant KPIs for the merchant portal and acquiring operations:
authorisation volume, requested value per currency, largest ticket, channel
mix and the share of requests that arrived with risk signals, per merchant, in
5-minute and 1-hour windows.

A Kafka Streams application reading `cards.authorisation.requested.v1`. KPIs
are held in windowed state stores and served over interactive queries; no
output topic.

Owned by **Payments Edge** (`@dss26-org/payments-edge`). Slack `#payments-edge`.

## Architecture

```
cards.authorisation.requested.v1 ──► filter tier=prod ──► re-key by merchant_id
        (application.id: merchant-analytics-stream)            │
                                                               ├─► merchant-kpi-5m  (tumbling 5 min, grace 2 min)
                                                               └─► merchant-kpi-1h  (tumbling 1 h,   grace 2 min)
                                                                        │
merchant-portal BFF ──► GET /merchants/{id}/kpis?window=5m|1h&hours=24 ◄┘
```

- Processing guarantee `exactly_once_v2`; one standby replica per store so a
  pod restart does not take the portal's KPIs offline while state restores.
- Internal topics (all prefixed `merchant-analytics-stream-`): the
  `by-merchant` repartition topic and one changelog per store.
- Unreadable records are logged and skipped
  (`LogAndContinueExceptionHandler`): these are statistics, not postings.
- Definitions of every KPI: [docs/kpis.md](docs/kpis.md).

## Events

| Direction | Topic | Group / application.id | Notes |
|-----------|-------|------------------------|-------|
| in | `cards.authorisation.requested.v1` | `merchant-analytics-stream` | Avro, reader schema `src/main/avro/cards.authorisation.requested.v1.avsc` |
| internal | `merchant-analytics-stream-by-merchant-repartition` | | keyed by `merchant_id` |
| internal | `merchant-analytics-stream-merchant-kpi-5m-changelog`, `...-1h-changelog` | | `MerchantKpi` (Avro, internal) |

We produce the authorisation topic too (merchant-gateway lives in this squad),
but this app only reads it.

## Build and run

```bash
mvn -B verify
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 SCHEMA_REGISTRY_URL=http://localhost:8081 \
KAFKA_SECURITY_PROTOCOL=PLAINTEXT APPLICATION_SERVER=localhost:8080 STATE_DIR=/tmp/mas \
java -jar target/merchant-analytics-stream-1.0.0-SNAPSHOT.jar
```

## Dashboards and alerts

- Datadog: [merchant-analytics-stream](https://app.datadoghq.eu/dashboard/p7m-2rw-c4h/merchant-analytics-stream)
  (records/s, punctuation latency, restore progress, IQ latency).
- Lag: Lenses, consumer group `merchant-analytics-stream` on `cards-prod-euw1`.
- Monitor (warn only, `#payments-edge`): lag above 50,000 for 15 minutes, or
  any stream thread in `DEAD` state.

## Runbooks

**Portal shows stale KPIs.** Check lag and the `state` gauge. During a
rebalance with standbys the switch is quick; a cold restore of the 1h store
takes up to 20 minutes.

**Resetting after a topology change.** Renaming a processor or a store changes
internal topic names. Stop every instance, then:

```bash
kafka-streams-application-reset --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
  --config-file client.properties --application-id merchant-analytics-stream \
  --input-topics cards.authorisation.requested.v1 --to-datetime <ISO-8601>
```

and delete the local state directories (`STATE_DIR`) before starting again.
The input topic keeps 7 days, so the hourly store can be rebuilt in full.

## On-call

Tier 3, business hours only. No paging; the merchant portal shows a "KPIs
delayed" banner when the endpoint is stale.
