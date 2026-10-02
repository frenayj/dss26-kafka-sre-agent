# merchant-gateway

The merchant and acquirer edge of the card authorisation flow. Acquirers send
authorisation requests to the gateway over REST; the gateway validates them and
publishes one `cards.authorisation.requested.v1` event per accepted request.
Fraud decisioning takes it from there.

Owned by **Payments Edge** (`@dss26-org/payments-edge`), Slack `#payments-edge`.
Tier 1: every change here is a change to the card authorisation path.

## API

`POST /v1/authorisations`

```json
{
  "merchantId": "mch_lumen_coffee",
  "cardToken": "tok_4410982",
  "amount": 42.50,
  "currency": "EUR",
  "merchantCountry": "FR",
  "riskSignals": ["VELOCITY_OK"],
  "channel": "CARD_PRESENT"
}
```

- `amount` is in major units, with no more decimal places than the currency
  allows (JPY 0, EUR 2, KWD 3).
- `channel` is one of `CARD_PRESENT`, `ECOM`, `RECURRING`, `MOTO`; default `ECOM`.
- `riskSignals` are the acquirer's own screening codes, forwarded as-is.

| Header | |
|---|---|
| `Idempotency-Key` | Optional. A retry with the same key and body returns the original `authId` and publishes nothing; keys are scoped per merchant and kept for 24h. |
| `X-Request-Id` | Optional. Copied onto the event as the `x-request-id` Kafka header. |

Errors are `application/problem+json` with a stable `code`:

| Status | `code` | When |
|---|---|---|
| 202 | | Published. Body `{"authId": "...", "status": "PENDING"}` |
| 400 | `validation_failed` | Missing or malformed fields, listed in `errors` |
| 409 | `idempotency_conflict` | `Idempotency-Key` reused with a different body |
| 422 | `invalid_amount_scale` | More decimal places than the currency allows |
| 429 | `rate_limited` | Merchant over its rate limit; honour `Retry-After` |
| 503 | `publish_failed` | Kafka did not acknowledge within 2s; retry with the same key |

## Events produced

| Topic | Key | Value |
|---|---|---|
| `cards.authorisation.requested.v1` | `card_token` | Avro record `com.dss26.payments.CardAuthEvent` |

Produced to `cards-prod-euw1` in production and `cards-dev-euw1` in development,
with `acks=all` and idempotence on. A 202 is only returned once the broker has
acknowledged the record.

Known consumers: `fraud-decisioning-engine` (fraud-decisioning-svc, Cards
Platform), `txn-history-builder`, `merchant-analytics-stream`.

## Schema ownership

Payments Edge owns the subject `cards.authorisation.requested.v1-value`. The
schema is [`src/main/avro/cards.authorisation.requested.v1.avsc`](src/main/avro/cards.authorisation.requested.v1.avsc).
The gateway builds its records from that file at runtime (no generated classes),
so the file is the contract.

The gateway never registers schemas. It runs with `auto.register.schemas=false`
and `use.latest.version=true`: it looks up the subject's latest registered
version and serialises with it.

### How a schema change ships

1. Change the `.avsc` in a pull request, following the cards
   [schema evolution policy](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980066817/Schema+evolution+policy+for+card+events)
   (add fields with defaults).
2. CI runs `schema-compat`, the shared workflow from `cards-ci-workflows`,
   against the subject.
3. On merge, the `release` workflow applies the subject's compatibility level
   from `<compatibilityLevels>` in `pom.xml` (`set-compatibility`), then
   registers the new version (`register`), both with the Confluent
   schema-registry Maven plugin, before the new image rolls out.
4. A schema change on a Tier-1 topic is a normal change: raise a CAB ticket and
   let the consumers above know in `#cards-platform`.

The subject is BACKWARD compatible, as the policy requires for `cards.*` subjects.

## Build and run

```
mvn verify              # unit tests; no Kafka or Schema Registry needed
```

Run locally against a broker and registry:

```
mvn -Dschema.registry.url=http://localhost:8081 \
    io.confluent:kafka-schema-registry-maven-plugin:register
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 SCHEMA_REGISTRY_URL=http://localhost:8081 \
    mvn spring-boot:run
```

| Variable | Default | |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | |
| `SCHEMA_REGISTRY_URL` | `http://localhost:8081` | |
| `GATEWAY_TIER` | `prod` | written to every event's `tier` |
| `GATEWAY_RATE_LIMIT_PER_SECOND` | `200` | per merchant, per pod |
| `GATEWAY_RATE_LIMIT_BURST` | `400` | |

## Runbooks and on-call

- Runbook: [docs/runbook.md](docs/runbook.md)
- PagerDuty: service `merchant-gateway` ([PSVC17D](https://dss26.pagerduty.com/service-directory/PSVC17D)), Payments Edge on-call
- Metrics and monitors: Datadog EU, `service:merchant-gateway`
- Slack: `#payments-edge`; during incidents `#sre-oncall`
