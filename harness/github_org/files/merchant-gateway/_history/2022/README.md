# merchant-gateway

Merchant and acquirer edge for card authorisations. Acquirers call the gateway
over REST; every accepted request is published as a
`cards.authorisation.requested.v1` event.

Owned by Payments Edge (`#payments-edge`).

## API

`POST /v1/authorisations`

```json
{
  "merchantId": "mch_lumen_coffee",
  "cardToken": "tok_4410982",
  "amount": 42.50,
  "currency": "EUR",
  "merchantCountry": "FR"
}
```

Returns `202 Accepted` with `{"authId": "...", "status": "PENDING"}`. A `400`
carries `{"code": "validation_failed", "errors": [...]}`; a `503` means Kafka did
not acknowledge in time and the request can be retried.

## Events

| Topic | Format | Consumers |
|---|---|---|
| `cards.authorisation.requested.v1` | Avro, Schema Registry ([ADR-0007](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980034049/ADR-0007+Avro+and+Schema+Registry+for+card+events)) | fraud-scoring |
| `acq.auth.requests` | JSON (legacy, until fraud-scoring has moved) | fraud-scoring |

Cluster: `kafka-dc1`. Keyed by card token, `acks=all`, idempotent producer.

## Schema

The value schema is `src/main/avro/cards.authorisation.requested.v1.avsc`,
subject `cards.authorisation.requested.v1-value`. The service reads the file at
runtime and never registers it (`auto.register.schemas=false`); the `release`
workflow registers it with the Confluent schema-registry Maven plugin on every
merge to `main`. New fields need a default.

## Build

```
mvn verify
```
