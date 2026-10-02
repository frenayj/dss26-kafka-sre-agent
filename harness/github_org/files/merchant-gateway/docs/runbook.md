# merchant-gateway runbook

Paging: PagerDuty service `merchant-gateway` (PSVC17D), Payments Edge on-call.
Dashboards, logs and monitors: Datadog EU, `service:merchant-gateway`.

## 5xx above 1% of requests

- **503 `publish_failed`**: Kafka did not acknowledge within `gateway.send-timeout`.
  Check producer latency and errors on the dashboard, then ask in
  `#cards-platform` whether `cards-prod-euw1` itself is healthy. The gateway does
  not buffer: acquirers retry with their `Idempotency-Key`, so nothing is lost
  while the cluster recovers.
- **500**: a bug. Find the stack trace in the logs and raise a PAY ticket.

## Schema lookup failures

Symptom: 503s, with `SerializationException` and a registry error such as
"Subject not found" in the logs.

The gateway serialises with the latest version registered for
`cards.authorisation.requested.v1-value` and never registers one itself. If the
subject or version is missing, re-run the `release` workflow for the current
commit on `main`: it registers the schema in `src/main/avro`. Do not turn on
`auto.register.schemas` in a running pod.

## One merchant getting 429s

Expected when a merchant retries in a tight loop. Confirm in the logs
(`code:rate_limited`, grouped by `merchant_id`) and tell the merchant's acquirer.
Limits are per pod (`GATEWAY_RATE_LIMIT_PER_SECOND`, `GATEWAY_RATE_LIMIT_BURST`);
raise them only with a PAY ticket.

## Rolling back a release

Revert the change on `main`; `release` rebuilds and redeploys the previous code.
Reverting a schema change also re-applies the compatibility level in `pom.xml`,
but a version that was already registered stays in the registry until Cards
Platform removes it.

## Escalation

1. Payments Edge on-call (PagerDuty).
2. marta.silva (tech lead, Payments Edge).
3. Problems on the consumer side of `cards.authorisation.requested.v1`
   (fraud-decisioning-svc and the other readers): Cards Platform on-call,
   escalation policy "Cards Platform - Primary", `#cards-platform`.
