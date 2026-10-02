# core-banking-adapter

The bridge between DSS26 Bank's services and the core ledger on the
mainframe. Everything that needs the core (balances, account opening, general
ledger postings) goes through this adapter over IBM MQ; nothing else talks to
the core queue manager.

Owned by **Core Banking** (`@dss26-org/core-banking`). Slack `#core-banking`.

## Interfaces

| Interface | Direction | Core program / copybook | Queues |
|-----------|-----------|-------------------------|--------|
| `GET /v1/accounts/{account}/balance` | sync | ACCTBAL1 | `DSS26.CORE.ACCT.BAL.REQ` / `.RPY` |
| `POST /v1/accounts` | sync | ACCTOPN1 | `DSS26.CORE.ACCT.OPEN.REQ` / `.RPY` |
| `ledger.journal.posted.v1` (group `core-banking-adapter`) | async | GLPOST01 | `DSS26.CORE.GL.POST.REQ` / `.RPY` |

- Messages are fixed-length EBCDIC (IBM-1047) records laid out by the
  copybooks in [`copybooks/`](copybooks); amounts are packed decimal (COMP-3).
  The copybooks are the contract with the mainframe team: changing one needs
  a CORE change request on their side first.
- **Idempotency**: the MQ correlation id is derived from the business id
  (journal id, customer + product). The core keeps a duplicate log and
  answers a repeated id with its original reply (RC 02 for postings), so
  Kafka redeliveries and client retries never post twice.
- **GL postings** are consumed one record at a time and a rejected posting
  stops the partition. Producers of `ledger.journal.posted.v1`:
  clearing-settlement-svc, disputes and fees (via Cards Platform).

## Batch window

The core runs its end-of-day batch 23:00-01:30 Europe/Paris. During the
window the GL request queue is not served; postings queue up in Kafka (lag on
`core-banking-adapter` grows, by design) and drain afterwards. Balance
enquiries are answered from the core's shadow copy.

## Dashboards

Datadog: [core-banking-adapter](https://app.datadoghq.eu/dashboard/x5c-1nt-g7w/core-banking-adapter)
(MQ round trip by queue, RC distribution, GL posting lag).

## On-call

Tier 1. PagerDuty service `PSVC5JB`, escalation policy "Core Banking -
Primary". Pages: GL posting lag above 20,000 outside the batch window, MQ
timeouts above 1% for 5 minutes. Mainframe operations bridge: `#core-ops`.
