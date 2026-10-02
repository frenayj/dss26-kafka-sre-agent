# merchant-gateway

Merchant and acquirer edge for card authorisations. Acquirers call the gateway
over REST; every accepted request is published to Kafka for fraud scoring.

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

Returns `202 Accepted` with `{"authId": "...", "status": "PENDING"}`, or `400`
when a field is missing or malformed.

## Kafka

Publishes JSON to `acq.auth.requests` on `kafka-dc1`, keyed by `cardToken`,
with `acks=all`. Consumed by fraud-scoring.

## Build

```
mvn verify
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 mvn spring-boot:run
```
