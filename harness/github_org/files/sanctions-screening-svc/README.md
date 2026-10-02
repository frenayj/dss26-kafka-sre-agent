# sanctions-screening-svc

Screens customer and counterparty names against the sanctions lists DSS26
Bank is bound by: OFAC SDN, the UN Security Council consolidated list, the EU
Financial Sanctions Files and the UK Sanctions List. Synchronous API for
onboarding and payments, plus rescreening when a customer's identifying data
changes.

Owned by **Compliance Platform** (`@dss26-org/compliance-platform`).
Slack `#compliance-platform`.

## How it works

- **Lists** (`internal/lists`) are downloaded at start-up and every 30
  minutes. If any list fails to load the previous complete set stays in use:
  never screen against a partial set. The service refuses to start without a
  first complete load.
- **Matching** (`internal/match`): names are folded (case, diacritics,
  punctuation, honorifics, legal forms) and scored with Jaro-Winkler against
  every name and alias. 0.88 and above is a potential match for an analyst.
- **API**: `POST /v1/screenings` with `customerId`, `name` and `trigger`
  (`ACCOUNT_OPEN`, `PERIODIC_REFRESH`, `CROSS_BORDER_TXN`,
  `BENEFICIARY_ADDED`). Called by kyc-onboarding-svc and payments-hub.
- **Rescreening**: consumer group `sanctions-screening-svc` on
  `customer.profile.updated.v1`; a change to name, date of birth,
  nationality or address triggers a new screening.

Every outcome is published to `sanctions.screening.completed.v1`, keyed by
customer.

## Events

| Direction | Topic | Group |
|-----------|-------|-------|
| in | `customer.profile.updated.v1` | `sanctions-screening-svc` |
| out | `sanctions.screening.completed.v1` | |

## Running

```bash
go test ./...
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 SCHEMA_REGISTRY_URL=http://localhost:8081 \
  go run ./cmd/sanctions-screening
```

## Dashboards

Datadog: [sanctions-screening](https://app.datadoghq.eu/dashboard/s3n-8jd-k5v/sanctions-screening)
(screenings/s, potential-match rate, list age per source).

## On-call

Tier 1: payments cannot leave without a screening. PagerDuty service
`PSVC9HM`, escalation policy "Compliance Platform - Primary". Pages when any
list is older than 6 hours or the API error rate is above 1%.
