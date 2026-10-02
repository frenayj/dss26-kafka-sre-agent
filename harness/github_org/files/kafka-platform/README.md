# kafka-platform

Topics, Schema Registry subjects, service accounts and ACLs for the cards
Kafka clusters, as code. Nothing on the clusters below is created or changed
by hand: open a pull request here, and the `apply` workflow makes the cluster
match `main`.

Owned by Platform Engineering (`@dss26-org/platform-engineering`). Domain
squads co-own their topics and service accounts through `CODEOWNERS`.

## Layout

```
teams.yaml                     squads that can own a topic or a service account
clusters/<cluster>.yaml        bootstrap servers, Schema Registry, replication minimum
topics/<domain>/<topic>.yaml   one file per topic
acls/<service-account>.yaml    one file per service account, with its ACLs
scripts/validate.py            the rules below - runs on every pull request
scripts/apply.py               plan / apply one cluster - runs on merge
docs/service-accounts.md       principals, credentials and ACL conventions
```

## Clusters

| Cluster | Environment | Notes |
|---|---|---|
| `cards-prod-euw1` | production | eu-west-1, brokers spread over three AZs, RF 3 minimum |
| `cards-dev-euw1` | development | eu-west-1, RF 3 minimum |

## Adding or changing a topic

Copy a file from the same domain folder and edit it. A topic file looks like
this:

```yaml
name: cards.authorisation.requested.v1
owner: cards-platform
tier: tier-1
description: >-
  Card authorisation request events from the merchant-acquirer gateway ...
clusters:
  - cards-prod-euw1
  - cards-dev-euw1
partitions: 3
replication_factor: 3
config:
  cleanup.policy: delete
  retention.ms: 604800000  # 7 days
  min.insync.replicas: 2
value_format: avro
schema:
  subject: cards.authorisation.requested.v1-value
  compatibility: BACKWARD
tags:
  - domain:cards
  - owner:cards-platform
  - criticality:tier-1
  - data-residency:eu
```

`scripts/validate.py` checks, on every pull request:

- the name follows `<domain>.<entity>.<event>.v<N>`, the file is called
  `<name>.yaml` and sits in `topics/<domain>/`;
- `owner` is a squad in `teams.yaml`, `tier` is `tier-1`, `tier-2` or `tier-3`;
- every cluster listed exists, `replication_factor` meets the cluster minimum
  and `min.insync.replicas` is lower than `replication_factor`;
- `cleanup.policy` and `retention.ms` are set;
- Avro topics declare their subject as `<name>-value` (one subject per topic,
  ADR-0007) and a compatibility level. Cards subjects are `BACKWARD` or
  stricter;
- `tags` carry `domain:`, `owner:`, `criticality:` and `data-residency:eu`,
  matching the file;
- a dead-letter topic is named `<topic>.dlq`, sets `dead_letter_for` to the
  topic it serves and stores raw bytes;
- ACLs only name declared topics, prefixed write grants never cover a
  catalogue topic, and wildcard (`"*"`) grants are read-only.

Run it locally before you push:

```sh
pip install -r requirements.txt
python3 scripts/validate.py
python3 -m unittest discover -s tests
```

### Partitions

Partitions can be added, never removed, and adding them moves keys to
different partitions - talk to the consumers of the topic first.

### Schema compatibility

Producers register their schemas (ADR-0007); the compatibility level of each
subject is owned here, and is set on the subject in each cluster's Schema
Registry when the change is applied, so a subject never silently falls back
to the registry default. If the registry refuses a new
schema at the declared level, the change needs a new topic version (`.v2`)
and a migration plan with the consumers - see the schema evolution policy in
the [DSS26 space](https://landoop.atlassian.net/wiki/spaces/DSS26/overview).

### Catalogue metadata

`description` and `tags` are what the Lenses topic catalogue shows. Keep the
description to what a consumer needs: producer, main consumers, retention and
anything unusual about the data.

## Requesting access for a service

Add or edit `acls/svc-<service>.yaml` (see
[docs/service-accounts.md](docs/service-accounts.md)). The squad that owns
the topic approves through `CODEOWNERS`. A new write grant on a tier-1 topic
in production is a normal change: link the CHG ticket in the pull request.

## How a change reaches the clusters

1. Open a pull request. `validate` runs the checks and the unit tests.
2. Platform Engineering and the owning squad approve (`CODEOWNERS`).
3. On merge, `apply` plans and applies `cards-dev-euw1`, then
   `cards-prod-euw1` once a platform engineer approves the
   `cards-prod-euw1` environment. The plan is in the job log.
4. `apply` never deletes. Removing a topic or an ACL is a manual change with
   a PLAT ticket; until then `apply` lists it as unmanaged.

## Contacts

- Slack: `#platform-engineering` (platform), `#cards-platform` (cards topics).
- Out of hours: PagerDuty service *Kafka Platform*, escalation policy
  *Platform Engineering - Primary*.
- Dashboards: Datadog EU, *Kafka / Cluster overview* and *Kafka / Consumers*.
