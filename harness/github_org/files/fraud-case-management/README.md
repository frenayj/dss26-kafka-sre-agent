# fraud-case-management

Opens, prioritises and closes fraud investigation cases for DSS26 Bank cards.
Cases come from two places: real-time fraud scores that need a human, and
cardholders who report fraud to the contact centre. Analysts work the queue in
the case management UI and resolve each case through this service.

Owned by **Risk Platform** (`@dss26-org/risk-platform`). Slack `#risk-platform`.

## Architecture

```
fraud-decisioning-svc ──► fraud.score.computed.v1
                                 │  consumer group: fraud-case-management
                                 ▼
                       triage (score, decision, rule matches)
                                 │ open?          ┌── txn-history-builder  GET /v1/transactions/{auth_id}
                                 ├────────────────┤
                                 │                └── card-lifecycle-svc   GET /v1/cards/{card_token}
                                 ▼
                       Postgres fraud_case ──► fraud.case.opened.v1
                                 ▲
analyst UI ──► POST /cases/{id}/resolution ──► fraud.case.resolved.v1
contact centre ──► POST /cases (cardholder report)
```

- **Triage** (`src/fraud_cases/triage.py`): every `DECLINE` opens a case
  (P1 when the score is 0.9 or more, or a high-risk rule fired); `REVIEW`
  opens P2/P3; `APPROVE` opens a P4 only when the score is above
  `FRAUD_CASES_REVIEW_THRESHOLD` (default 0.5).
- **At-least-once**: the offset is committed after the case row and the
  `fraud.case.opened.v1` event are both done. `triggering_auth_id` is unique,
  so a replayed score never opens a second case.
- Score events only carry `auth_id`; the card token and customer come from
  the cards servicing read APIs.

## Events

| Direction | Topic | Group | Schema |
|-----------|-------|-------|--------|
| in | `fraud.score.computed.v1` | `fraud-case-management` | `schemas/fraud.score.computed.v1.avsc` |
| out | `fraud.case.opened.v1` | | `schemas/fraud.case.opened.v1.avsc` |
| out | `fraud.case.resolved.v1` | | `schemas/fraud.case.resolved.v1.avsc` |

`fraud.score.computed.v1` is produced by fraud-decisioning-svc (Cards
Platform; called fraud-scoring before ADR-0011). Risk Platform owns the
schema because we own the scoring models.

## Running

```bash
pip install -e '.[dev]'
pytest -q
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 SCHEMA_REGISTRY_URL=http://localhost:8081 \
KAFKA_SECURITY_PROTOCOL=PLAINTEXT FRAUD_CASES_DB_URL=postgresql://localhost/fraud_cases \
fraud-cases-consumer
uvicorn fraud_cases.api:app --port 8080
```

## Dashboards

- Datadog: [fraud-case-management](https://app.datadoghq.eu/dashboard/m5q-7tc-w9a/fraud-case-management)
  (cases opened per priority, queue age, consumer lag).
- Lenses: group `fraud-case-management` on `cards-prod-euw1`.

## Runbooks

**Cases stopped appearing.** First check whether scores are arriving at all
(Lenses, `fraud.score.computed.v1` produce rate). No scores means the problem
is upstream in fraud decisioning, not here. Scores arriving but lag growing:
check the lookup calls in the logs (`txn-history-builder` or
`card-lifecycle-svc` timing out).

**Queue too long for the analysts.** Raise `FRAUD_CASES_REVIEW_THRESHOLD`
temporarily (stops new P4s) and tell `#fraud-ops`.

## On-call

Tier 2. Business hours: Risk Platform. Fraud operations work the queue 24/7;
they escalate to `#risk-platform` and, out of hours, to `#sre-oncall`.
