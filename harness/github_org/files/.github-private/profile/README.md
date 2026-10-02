# DSS26 Bank Engineering

This page is only visible to members of the **dss26-org** organisation.

DSS26 Bank is a European retail bank: current accounts, cards, savings and
payments for personal and small-business customers across the EU. Engineering
is organised in four tribes of long-lived squads. Each squad owns its services
end to end - build, run, on-call - and its repositories in this organisation.

## Tribes and squads

### Cards & Payments

Card acquiring, issuing, authorisation, clearing and settlement.

| Squad | Owns | Main repositories | Slack |
|---|---|---|---|
| Payments Edge | Merchant and acquirer edge, producer of `cards.authorisation.requested.v1` | [merchant-gateway](https://github.com/dss26-org/merchant-gateway), [merchant-analytics-stream](https://github.com/dss26-org/merchant-analytics-stream) | `#payments-edge` |
| Cards Platform | Authorisation, fraud decisioning and ledger posting on the cards Kafka clusters | [fraud-decisioning-svc](https://github.com/dss26-org/fraud-decisioning-svc), [cards-ci-workflows](https://github.com/dss26-org/cards-ci-workflows) | `#cards-platform` |
| Cards Servicing | Card lifecycle, disputes, refunds, statements and transaction history | [card-lifecycle-svc](https://github.com/dss26-org/card-lifecycle-svc), [disputes-svc](https://github.com/dss26-org/disputes-svc), [txn-history-builder](https://github.com/dss26-org/txn-history-builder) | `#cards-servicing` |
| Clearing & Settlement | Scheme clearing files, settlement batches and interchange | [clearing-settlement-svc](https://github.com/dss26-org/clearing-settlement-svc) | `#clearing-settlement` |

### Financial Crime & Risk

Fraud, AML, sanctions and KYC.

| Squad | Owns | Main repositories | Slack |
|---|---|---|---|
| Risk Platform | Fraud case management, risk limits and fraud scoring models | [fraud-case-management](https://github.com/dss26-org/fraud-case-management) | `#risk-platform` |
| Compliance Platform | AML transaction screening, sanctions screening and KYC | [team repositories](https://github.com/orgs/dss26-org/teams/compliance-platform/repositories) | `#compliance-platform` |

### Customer & Channels

Customer data, consent, mobile and internet banking.

| Squad | Owns | Main repositories | Slack |
|---|---|---|---|
| Customer Platform | Customer profile, accounts and consent | [team repositories](https://github.com/orgs/dss26-org/teams/customer-platform/repositories) | `#customer-platform` |
| Digital Channels | Mobile and internet banking | [team repositories](https://github.com/orgs/dss26-org/teams/digital-channels/repositories) | `#digital-channels` |

### Core Technology

Core banking integration, payment rails and the engineering platforms.

| Squad | Owns | Main repositories | Slack |
|---|---|---|---|
| Core Banking | Core banking adapter and the SEPA / SWIFT payments hub | [team repositories](https://github.com/orgs/dss26-org/teams/core-banking/repositories) | `#core-banking` |
| Platform Engineering | Kafka platform, CI templates, golden paths and developer tooling | [kafka-platform](https://github.com/dss26-org/kafka-platform) | `#platform-engineering` |

## How we work

- **Decisions** are ADRs in the owning squad's Confluence space (`ADR-NNNN`),
  linked from the README of every repository they affect. Read the ADRs
  before you change how a service talks to Kafka.
- **Runbooks** live in Confluence next to the service page. Every alert links
  the runbook it expects you to follow; if the runbook is wrong, fixing it is
  part of closing the incident.
- **Kafka** topics, Schema Registry compatibility, service accounts and ACLs
  are code in [kafka-platform](https://github.com/dss26-org/kafka-platform).
  Nobody changes a cluster by hand.
- **Lenses** is the Kafka console for every environment: topics, schemas,
  consumer groups and connectors. Access is by SSO group; write access is
  time-boxed and approved.
- **Observability** is Datadog, EU site: metrics, logs, APM and monitors.
  Dashboards and monitors are named after the service.
- **On-call** is PagerDuty. Every Tier-1 service has a PagerDuty service and
  an escalation policy (for example *Cards Platform - Primary*). During an
  incident, talk in `#sre-oncall`; afterwards write a blameless postmortem
  from the template in Confluence (`INC-YYYY-MM-DD-NNN`).
- **Change management**: a change to a Tier-1 card flow (label `tier-1`) is a
  normal change - a CHG ticket approved at CAB (Tuesdays and Thursdays) before
  it ships. Changes that follow a documented, pre-approved path are standard
  changes and need no CAB.
- **Card data**: topics, logs and tickets carry `card_token`, never a PAN
  (PCI DSS). Never paste a message payload into a ticket or into Slack.
  Questions to `#compliance-cards`.

## Golden paths

| I want to... | Start here |
|---|---|
| Add a Kafka topic or give a service access | Pull request to [kafka-platform](https://github.com/dss26-org/kafka-platform) - `topics/` or `acls/` |
| Change an Avro schema on a cards topic | Call `schema-compat` from [cards-ci-workflows](https://github.com/dss26-org/cards-ci-workflows) in your CI, one subject per topic, `BACKWARD` compatible |
| Build a Java service | The `java-build` reusable workflow in [cards-ci-workflows](https://github.com/dss26-org/cards-ci-workflows) |
| Put a service in the catalogue | A `catalog-info.yaml` at the repository root; Backstage picks it up |
| Make sure the right people review | `.github/CODEOWNERS` with team handles (`@dss26-org/<squad>`), never individuals |

## New here?

1. Ask your squad lead to add you to your squad's GitHub team; repository
   access follows the team.
2. Request the `engineering-all` SSO group, plus your squad's Lenses group.
3. Join `#engineering`, your squad's channel and `#sre-oncall`.
4. Read your squad's Confluence space home, its ADRs and its on-call page,
   then shadow one on-call week before you take one.

## Useful links

- Confluence: [DSS26 - Cards Platform Engineering](https://landoop.atlassian.net/wiki/spaces/DSS26/overview)
- Jira: one project per tribe (`CARDS`, `PAY`, `RISK`, ...), plus `CHG` for CAB tickets
- Datadog (EU): <https://app.datadoghq.eu>
- PagerDuty: <https://dss26.pagerduty.com>
- Backstage catalogue: <https://backstage.dss26.internal>
- Lenses: <https://lenses.dss26.internal>

Questions about this page: `#platform-engineering`.
