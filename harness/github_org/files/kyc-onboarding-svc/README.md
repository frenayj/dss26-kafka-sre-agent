# kyc-onboarding-svc

Know-your-customer checks for new DSS26 Bank customers. The onboarding
journeys in the apps hand over once the applicant has finished the identity
step with the IDV provider; this service collects the IDV report, screens the
applicant against the sanctions lists, rates the customer's risk, and
publishes the outcome on `kyc.verification.completed.v1`. customer-profile-svc
opens the account from that event.

Owned by **Compliance Platform** (`@dss26-org/compliance-platform`).
Slack `#compliance-platform`.

## Flow

```
app onboarding ──► POST /v1/applications/{id}/verification
                        │
                        ├── IDV provider report (document, face match, liveness)
                        ├── sanctions-screening-svc  POST /v1/screenings (ACCOUNT_OPEN)
                        ├── RiskRater (LOW / MEDIUM / HIGH)
                        ▼
                  Postgres kyc_verification ──► kyc.verification.completed.v1 (after commit)
                                                        │
                                                        └──► customer-profile-svc (opens the account)
```

- **Outcome**: FAIL when the document or liveness check fails; MANUAL_REVIEW
  on a weak face match or a potential sanctions match; otherwise PASS.
- **Risk rating** (`verification/RiskRater.kt`): PEP status, high-risk third
  countries, residence outside the EEA, potential sanctions match; electronic
  ID or in-branch identification lowers residual risk by one step.
- **Periodic review**: verifications expire after 1 year (HIGH), 3 years
  (MEDIUM) or 5 years (LOW). A nightly job opens refresh tasks 30 days ahead.

## Events

| Direction | Topic | Notes |
|-----------|-------|-------|
| out | `kyc.verification.completed.v1` | keyed by customer_id, sent after commit |

## Data retention

KYC records are kept for five years after the end of the business
relationship, then deleted by the retention job in customer-profile-svc's
erasure workflow. IDV images are never stored here; only the provider's
report reference. From July 2027 the AML Regulation (EU) 2024/1624 replaces
the directive's national rules; Compliance tracks the mapping in CMP-1310.

## Dashboards

Datadog: [kyc-onboarding](https://app.datadoghq.eu/dashboard/b6k-2mp-z8r/kyc-onboarding)
(verifications per outcome, manual review queue, IDV latency).

## On-call

Tier 1: account opening stops without it. PagerDuty service `PSVC2XF`,
escalation policy "Compliance Platform - Primary".
