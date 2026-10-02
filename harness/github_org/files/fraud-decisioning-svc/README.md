# fraud-decisioning-svc

Tier-1 service that approves, sends to review or declines every card
authorisation, and posts the result to the ledger.

| | |
|---|---|
| Consumes | `cards.authorisation.requested.v1` (producer: merchant-gateway, payments-edge) |
| Consumer group | `fraud-decisioning-engine` on `cards-prod-euw1` |
| Produces | `cards.ledger.posted.v1` (read by the General Ledger) |
| Owner | Cards Platform - alex.chen (lead), priya.r, jordan.k |
| Paging | PagerDuty service `PSVC42A`, escalation policy "Cards Platform - Primary" |
| Slack | `#cards-platform` (`#sre-oncall` during incidents) |

Formerly **fraud-scoring** with consumer group `fraud-scoring-consumer`. Both
were renamed when the service took over approve/decline decisions
([ADR-0011](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3979247620/ADR-0011+Rename+fraud-scoring+to+fraud-decisioning), completed June 2024).
The old group was deleted; anything still mentioning it is out of date.

## How it works

```
merchant-gateway --> cards.authorisation.requested.v1 --> fraud-decisioning-svc --> cards.ledger.posted.v1
                     (Avro, Schema Registry)               decide: APPROVE |         (Avro, posting_id =
                                                           REVIEW | DECLINE          uuid5(auth_id))
```

For each batch the decisioning loop (`fraud_decisioning/consumer.py`):

1. reads up to `BATCH_SIZE` records and deserialises each one with the
   **pinned reader schema** `schemas/cards_authorisation_requested_v1.avsc`;
2. scores it (`fraud_decisioning/scoring.py`: channel base rate, amount band,
   cross-border weight, risk signals) and maps the result to a ledger posting
   (`fraud_decisioning/ledger.py`);
3. produces the postings with `acks=all` and an idempotent producer, and waits
   for every acknowledgement;
4. commits, per partition, the offset after the last record it posted.

Offsets are committed manually and only in step 4. `enable.auto.commit` is
forced to `false`; the service refuses to start if the deployed properties say
otherwise.

`posting_id` is derived from `auth_id`, so a record that is read twice (after
a restart or a rebalance) produces the same posting id and the General Ledger
de-duplicates it.

## Fail closed

If a record cannot be deserialised with the pinned reader schema, the service
does **not** skip it. The partition is paused at that offset, the error is
logged with the writer schema id from the record header, and the partition is
retried every `BLOCKED_RETRY_SECONDS` (default 5). Nothing at or after that
offset is committed until the record can be read. Other partitions keep
flowing.

Why: every authorisation must end in exactly one decision and one ledger
posting. A record we cannot read has no amount, no merchant and no risk
signals we can trust. Approving it would let an unscored payment through;
declining it would decline a customer's card for a reason that has nothing to
do with the customer; skipping it would leave an authorisation with no
decision and a hole in the ledger. None of those is acceptable, so the
partition waits and the lag alert pages a human.

What it looks like when it happens:

- `fraud_decisioning_blocked_partitions` > 0 and
  `fraud_decisioning_deserialisation_errors_total` rising for one or more
  partitions;
- consumer lag on `cards.authorisation.requested.v1` growing on those
  partitions only, with the committed offset frozen;
- postings to `cards.ledger.posted.v1` dropping in proportion;
- log lines `cannot read cards.authorisation.requested.v1[<p>]@<offset> (writer schema id <id>, ...)`.

Scaling out or restarting does not help: the record is still there. Find out
which writer schema produced it and fix the schema (or the reader) first.

## Schemas

| File | Role |
|---|---|
| `schemas/cards_authorisation_requested_v1.avsc` | Reader schema we pin for `cards.authorisation.requested.v1`. Same as the v1 producer schema owned by payments-edge. |
| `schemas/cards_ledger_posted_v1.avsc` | Writer schema for `cards.ledger.posted.v1`. We own it; CI checks it against the registry (`schema-compat` job). |

Producers may add fields with defaults without telling us. Anything else on
the authorisation topic (a type change, a removed field without a default)
needs a reader change here, deployed **before** the producer starts writing
the new version. See the [schema evolution policy](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980066817/Schema+evolution+policy+for+card+events)
([ADR-0007](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980034049/ADR-0007+Avro+and+Schema+Registry+for+card+events)).

## Configuration

| Variable | Default | |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | - | required |
| `SCHEMA_REGISTRY_URL` | - | required |
| `KAFKA_CONSUMER_PROPERTIES` | - | properties file rendered from `kafka.consumer` in the Helm values |
| `INPUT_TOPIC` | `cards.authorisation.requested.v1` | |
| `LEDGER_TOPIC` | `cards.ledger.posted.v1` | |
| `READER_SCHEMA_PATH` / `LEDGER_SCHEMA_PATH` | `schemas/...` | |
| `BATCH_SIZE` | `500` | was 2000 until INC-2025-03-18-002 |
| `BLOCKED_RETRY_SECONDS` | `5` | |
| `METRICS_PORT` | `9102` | Prometheus `/metrics` |

Consumer settings (`group.id`, `session.timeout.ms`, `max.poll.interval.ms`,
...) live in `deploy/helm/values-<env>.yaml` under `kafka.consumer`.
`max.poll.interval.ms` was raised to 300000 after
[INC-2025-03-18-002](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980263426/INC-2025-03-18-002+fraud-decisioning+lag+during+a+rebalance+storm)
(rebalance storm); see also the
[rebalance runbook](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980165121/Runbook+Consumer+group+rebalance+storms).

## Development

```
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest
```

The unit tests need no broker or registry. To run against `cards-dev-euw1`,
use your own consumer group so you never move the production group's offsets:

```
KAFKA_BOOTSTRAP_SERVERS=demo-kafka-dev:9092 \
SCHEMA_REGISTRY_URL=http://demo-kafka-dev:8081 \
KAFKA_CONSUMER_PROPERTIES=<(echo group.id=fraud-decisioning-local-$USER) \
python -m fraud_decisioning
```

## Deployment

`main` builds `harbor.dss26.internal/cards-platform/fraud-decisioning-svc:<sha>`
and the cards-platform release pipeline rolls it out with the platform
`kafka-service` Helm chart and the values in `deploy/helm/`. This is a Tier-1
flow: production changes need a CHG ticket in the PR description.

## Monitoring

- Datadog EU, dashboard "fraud-decisioning-svc".
- Monitors are managed in `monitoring/` (Terraform). `kafka_consumer_lag`
  pages PagerDuty `PSVC42A` above 50,000 records of lag on
  `cards.authorisation.requested.v1`.
- Service metrics: `fraud_decisioning_*` on `:9102/metrics`, scraped by the
  Datadog OpenMetrics check.
