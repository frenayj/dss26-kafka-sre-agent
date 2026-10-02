# txn-history-builder

Builds the cardholder transaction history that the mobile and internet banking
apps show under **Cards > Transactions**. It consumes every authorisation
request from `cards.authorisation.requested.v1`, keeps one row per `auth_id`
in Postgres, and serves the history to the channel BFFs over a small read API.

Owned by **Cards Servicing**. Slack `#cards-servicing`.

## Architecture

```
merchant-gateway ──► cards.authorisation.requested.v1 (Avro, cards-prod-euw1)
                              │
                              │  consumer group: txn-history-builder
                              ▼
                     txn-history-builder ──► Postgres (txn_history.card_transaction)
                              │
                              ├──► GET /v1/cards/{cardToken}/transactions   (mobile BFF, web BFF)
                              └──► GET /v1/transactions/{authId}            (fraud-case-management)
```

- **Listener** (`kafka/AuthorisationListener.kt`): batch listener, 3 consumers
  per pod. Each poll is written with one JDBC batch upsert; the batch commits
  its offsets only after the insert succeeds.
- **Idempotent writes**: `auth_id` is the primary key and the insert is
  `ON CONFLICT DO NOTHING`, so a replay or a rebalance never duplicates a row.
- **Tier filter**: the producer stamps `tier` on every record. Only `prod`
  records reach the table (`txn-history.accepted-tiers`).
- **Unreadable records** are retried twice, then logged and counted
  (`txn_history.records.skipped`) instead of blocking the partition. The
  nightly clearing reconciliation in card-statements-batch backfills anything
  we skipped.
- **Read API** (`api/TransactionHistoryController.kt`): newest first, keyset
  pagination on `authorised_at` (`?before=<ISO-8601>&limit=50`). Risk
  Platform's fraud-case-management looks single authorisations up by
  `auth_id`.

`card-statements-batch` reads the same table from the read replica to build
monthly statements. Schema changes here need a heads-up in `#cards-servicing`.

## Events

| Direction | Topic | Group | Schema |
|-----------|-------|-------|--------|
| in | `cards.authorisation.requested.v1` | `txn-history-builder` | `src/main/avro/cards.authorisation.requested.v1.avsc` (copy of the producer's v1, generated as `com.dss26.payments.CardAuthEvent`) |

We produce nothing. The topic is produced by merchant-gateway (Payments Edge)
and catalogued by Cards Platform; schema questions go to `#payments-edge`.
Serialisation follows [ADR-0007](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980034049/ADR-0007+Avro+and+Schema+Registry+for+card+events)
(Avro, Schema Registry, one subject per topic value).

## Running locally

```bash
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export SCHEMA_REGISTRY_URL=http://localhost:8081
export KAFKA_SECURITY_PROTOCOL=PLAINTEXT
export TXN_HISTORY_DB_URL=jdbc:postgresql://localhost:5432/txn_history
export TXN_HISTORY_DB_USER=txn_history TXN_HISTORY_DB_PASSWORD=txn_history
gradle bootRun
```

Flyway applies `src/main/resources/db/migration` on start-up.

## Dashboards and alerts

- Datadog: [txn-history-builder](https://app.datadoghq.eu/dashboard/k3x-9qd-2mf/txn-history-builder)
  (write rate, batch size, skipped records, API latency).
- Consumer lag: Lenses, group `txn-history-builder` on `cards-prod-euw1`.
- Monitors (warn to `#cards-servicing`, no page):
  - `kafka.consumer_lag{consumer_group:txn-history-builder}` above 20,000 for 10 minutes.
  - `txn_history.records.skipped` above 0 over 15 minutes.

## Runbooks

[docs/runbook.md](docs/runbook.md): lag, skipped records, replaying a time
range.

## On-call

Tier 2. Business hours: Cards Servicing (`@dss26-org/cards-servicing`).
Out of hours nobody is paged for this service; the apps fall back to showing
statement transactions only. Escalate through `#sre-oncall` if the read API
itself is down.
