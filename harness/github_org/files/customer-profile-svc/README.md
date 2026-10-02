# customer-profile-svc

The customer master for DSS26 Bank: name, contact data, marketing
preferences and consents, plus opening the first account once KYC passes.
Every change to a profile or a consent is published so downstream systems
(audit log, contact-data consumers, sanctions rescreening) never poll.

Owned by **Customer Platform** (`@dss26-org/customer-platform`).
Slack `#customer-platform`.

## API

| Method | Path | |
|--------|------|-|
| GET | `/v1/customers/{id}` | profile |
| PUT | `/v1/customers/{id}` | update; `X-Changed-By` set by the channel or the contact-centre desktop |
| POST | `/v1/customers/{id}/consents` | grant a consent (PSD2, marketing, data sharing) |
| DELETE | `/v1/customers/{id}` | GDPR erasure, deferred while retention periods run |

## Events

| Direction | Topic | Group / notes |
|-----------|-------|---------------|
| in | `kyc.verification.completed.v1` | `customer-profile-svc`; PASS opens the current account |
| out | `customer.account.opened.v1` | account number allocated by the core ledger via core-banking-adapter |
| out | `customer.profile.updated.v1` | `changed_fields` uses snake_case field names |
| out | `customer.consent.granted.v1` | PSD2 AISP consents expire after 180 days |

All events are keyed by customer id and sent after the database commit.

## Privacy

Profiles hold personal data (GDPR). Erasure overwrites personal fields and
keeps the customer id; it is refused while an account is open or closed less
than five years ago (AML record keeping). Events carry ids and field names,
never the values.

## Dashboards

Datadog: [customer-profile](https://app.datadoghq.eu/dashboard/f2x-9qa-h4m/customer-profile).

## On-call

Tier 2. Business hours: Customer Platform. Account opening failures out of
hours queue up on `kyc.verification.completed.v1` and are processed on
restart.
