# txn-history-builder runbook

## Lag warning on `txn-history-builder`

Lag on this group only delays what the apps show; nothing downstream posts
money from it.

1. Lenses > `cards-prod-euw1` > consumer groups > `txn-history-builder`. Check
   whether lag is spread across partitions (throughput) or sits on one
   partition (a slow or failing batch).
2. Datadog dashboard: compare `txn_history.batch.size` and the Postgres write
   latency panel. If Postgres is slow, lag follows; fix the database first.
3. Throughput: raise `replicaCount` (up to the partition count divided by
   the listener concurrency of 3) in `deploy/values-prod.yaml`.

## `txn_history.records.skipped` above zero

A record failed to deserialise three times and was skipped. The log line
`Skipping <topic>-<partition>@<offset>` names it. Look the offset up in
Lenses. If it is a one-off, nothing to do: the nightly reconciliation
backfills the transaction. If many records are skipped, ask `#payments-edge`
whether the producer schema changed.

## Replaying a time range

Rows are keyed on `auth_id` and the insert ignores duplicates, so a replay is
safe.

1. Scale the deployment to 0 (the group must have no active members).
2. Reset offsets:

   ```bash
   kafka-consumer-groups --bootstrap-server "$KAFKA_BOOTSTRAP_SERVERS" \
     --command-config client.properties \
     --group txn-history-builder --topic cards.authorisation.requested.v1 \
     --reset-offsets --to-datetime 2026-01-01T00:00:00.000 --execute
   ```

3. Scale back up and watch lag drain.

Retention on the topic is 7 days; older history comes from the clearing
reconciliation, not from Kafka.
