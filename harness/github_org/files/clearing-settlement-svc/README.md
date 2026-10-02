# clearing-settlement-svc

Card scheme clearing for DSS26 Bank: ingests the Visa Base II and Mastercard
IPM presentments, matches each one to its authorisation, calculates
interchange and scheme fees, and runs the daily merchant settlement that
funds merchants and posts the general ledger.

Owned by **Clearing & Settlement** (`@dss26-org/clearing-settlement`).
Slack `#clearing-settlement`.

## Architecture

```
scheme gateway (MFT) ──► *.base2.psv / *.ipm.psv
                               │  ClearingFileIngestor (every minute)
                               ▼
                     cards.clearing.received.v1
                               │  ClearingMatcher (group clearing-settlement-matcher)
                               │    └─ issuer_auth_log (replica of the authorisation host)
                               ▼
                     cards.clearing.matched.v1 ──► sink-gcs-clearing-archive (Cards Platform)
                               │  FeeListener (group clearing-settlement-fees)
                               ▼
                     cards.interchange.fee.calculated.v1
                               │
          22:00 Europe/Paris, T2 business days: SettlementBatchJob
                               ├──► cards.settlement.batch.posted.v1   (one per merchant and currency)
                               └──► ledger.journal.posted.v1           (scheme clearing -> merchant payable)
```

- **Matching** (`MatchScorer`): same card, merchant and currency, then the
  amount. Exact amounts score 1.0. Hotels, car hire, restaurants and bars may
  clear up to 15% above or below the authorisation. Below 0.8 the presentment
  goes to the exceptions queue (`status = 'UNMATCHED'`) for the back office.
- **Fees** (`InterchangeCalculator`): IFR caps inside the EEA (0.2% consumer
  debit, 0.3% consumer credit), the 2019 scheme commitments for
  inter-regional consumer cards, scheme table rate for commercial cards.
- **Settlement** never runs on a TARGET closing day (`TargetCalendar`).

## Events

| Direction | Topic | Group | Schema |
|-----------|-------|-------|--------|
| out | `cards.clearing.received.v1` | | `src/main/avro/cards.clearing.received.v1.avsc` |
| in | `cards.clearing.received.v1` | `clearing-settlement-matcher` | |
| out | `cards.clearing.matched.v1` | | `src/main/avro/cards.clearing.matched.v1.avsc` |
| in | `cards.clearing.matched.v1` | `clearing-settlement-fees` | |
| out | `cards.interchange.fee.calculated.v1` | | `src/main/avro/cards.interchange.fee.calculated.v1.avsc` |
| out | `cards.settlement.batch.posted.v1` | | `src/main/avro/cards.settlement.batch.posted.v1.avsc` |
| out | `ledger.journal.posted.v1` | | owned by Cards Platform; we use the latest registered version |

Other readers of `cards.clearing.matched.v1`: the clearing archive connector
and aml-transaction-screening. Treat the schemas above as a contract.

## Schema changes

1. Change the `.avsc` here. Fields you add need a default; never remove or
   retype a field on a `.v1` topic.
2. CI runs the shared `schema-compat` workflow from `dss26-org/cards-ci-workflows`
   against the registry for every subject listed in `.github/workflows/ci.yml`.
3. Normal change on a Tier-1 topic: CAB ticket and a named approver (see the
   change management standard in the DSS26 space).
4. The producer does not auto-register (`auto.register.schemas=false`):
   register the new version in uat and prod before deploying.

## Dashboards and alerts

- Datadog: [clearing-settlement](https://app.datadoghq.eu/dashboard/h4t-6zb-m2q/clearing-settlement)
  (presentments per cycle, match rate, unmatched queue, settlement run).
- Lenses: groups `clearing-settlement-matcher` and `clearing-settlement-fees`
  on `cards-prod-euw1`.
- Paging monitors: no clearing file ingested by 07:00 on a business day; match
  rate below 97% over a cycle; settlement run not finished by 23:30.

## Runbooks

- [Settlement run did not finish](docs/runbook.md#settlement-run-did-not-finish)
- [Unmatched queue growing](docs/runbook.md#unmatched-queue-growing)

## On-call

Tier 1. PagerDuty service `PSVC3WN`, escalation policy "Clearing &
Settlement - Primary". Settlement problems after 22:00 also go to Treasury
operations (`#treasury-ops`): merchant funding leaves at 06:00.
