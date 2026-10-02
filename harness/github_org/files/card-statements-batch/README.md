# card-statements-batch

Monthly card statements for DSS26 Bank cardholders, and the nightly
reconciliation that keeps the card transaction history complete. Spring
Batch, run as Kubernetes CronJobs.

Owned by **Cards Servicing** (`@dss26-org/cards-servicing`).
Slack `#cards-servicing`.

## Jobs

| Job | Schedule (Europe/Paris) | What it does |
|-----|-------------------------|--------------|
| `transactionReconciliationJob` | daily 02:00 | Backfills `card_transaction` (txn-history-builder's table) with authorisations that cleared yesterday but are missing, and marks cleared rows SETTLED. |
| `monthlyStatementJob` | 1st of the month 03:00, `period=YYYY-MM` | One PDF per card with activity or a balance, to the document archive (S3, KMS-encrypted), then `cards.statement.generated.v1`. |

The statement job is partitioned by issuing BIN range: eight workers over
disjoint cards. A chunk (100 cards) commits only after every PDF is stored
and every event acknowledged; a restart with the same `period` resumes from
the last committed chunk.

## Events

| Direction | Topic | Notes |
|-----------|-------|-------|
| out | `cards.statement.generated.v1` | keyed by customer; read by notifications and the apps |

## Data sources

- `statement_cycle` (own database): which cards close a cycle in a period.
- `card_transaction` on the **txn-history-builder read replica** (read), and
  on its primary (write, reconciliation only, dedicated role).
- `clearing_replica.cleared_yesterday`: view on the clearing-settlement
  replica.

## Runbooks

**Statement run failed.** Check the job execution in the batch tables
(`BATCH_JOB_EXECUTION`). Fix the cause and rerun with the same `period`;
completed partitions are not redone. Statements must be available by the 3rd
(card terms and conditions).

**Reconciliation backfilled a lot of rows.** That means txn-history-builder
skipped or missed records the day before; look at its
`txn_history.records.skipped` metric and its consumer group lag.

## On-call

Tier 3. Business hours: Cards Servicing.
