# The incident

One deterministic incident ships with the demo, the `consumer-lag` scenario
([`harness/scenarios/consumer-lag/`](../harness/scenarios/consumer-lag)).
`make induce` breaks exactly one thing on the cluster and `make reset`
restores it, so you can run it at any time. Scenarios are folders, so you can
[add your own](../harness/scenarios/README.md#adding-a-scenario) without
touching the agent.

| | **PI7K3FQ: consumer lag** |
|---|---|
| Alert | `kafka_consumer_lag` CRITICAL on `fraud-decisioning-engine` |
| Trigger | `make induce` registers an incompatible v2 Avro schema |
| What breaks | The consumer wedges on the first v2 record: lag grows and ledger postings stop |
| Culprit | a `merchant-gateway` PR: `amount` becomes a decimal string, `country` is dropped, and the subject's compatibility is set to `NONE` |
| Skills it exercises | `kafka-incident-rca`, `kafka-schema-review` |

## Running it

From the dashboard (http://localhost:8080):

```sh
make induce              # break the cluster
# pick PI7K3FQ in the dashboard and press Run
make reset               # restore it
```

From the terminal, with the host venv (`make venv`):

```sh
make scenario            # reset -> induce -> run the agent on the alert
```

Every scenario target takes `SCENARIO=<folder>`, `consumer-lag` by default.
With real PagerDuty, the page itself starts the run: see
[Going live](going-live.md#pagerduty).

## The operator console

`make ops` starts a small server on the host (http://127.0.0.1:8770) behind
the dashboard's unlisted page **http://localhost:8080/#/ops**. The page
shows the live state of everything a scenario touches - consumer lag, the
schema's version and compatibility, connector and task states, whether each
culprit PR is on `main`, open PagerDuty incidents, the agent's queue and
last run, container health - and has a button for each step, with the
command's output streaming underneath and a Stop button.

Its **Models** card picks the model each agent runs on. It's the same
setting as the dashboard's Models panel, held by the agent server, so the
run a page starts uses whatever either one shows.

| Button | Runs |
|---|---|
| *Consumer lag incident* | `make live SCENARIO=consumer-lag`: reset, resolve old pages, induce, wait, page |
| Reset | `make reset` |
| Resolve pages | `make pd-resolve` |
| Break: consumer lag | `make induce SCENARIO=consumer-lag` |
| Page: consumer lag | `make page SCENARIO=consumer-lag` |
| Merge decoy PRs | `make gh-warmup` |
| Preflight | `make preflight` |

Each scenario folder adds its own three buttons (the live run, the break and
the page). The server runs the same `make` targets you would type, one at a
time, with your Docker CLI and `gh` login
([`harness/ops/ops_server.py`](../harness/ops/ops_server.py)). It listens
on 127.0.0.1 only and accepts actions only from the dashboard's own origins.

## What the alert knows, and what the agent has to find

The alert
([`incident.json`](../harness/scenarios/consumer-lag/incident.json)) carries
only what a Datadog monitor would attach: the monitor, the metric value
against its threshold, the monitor's tags (cluster, consumer group, topic,
service, team) and a runbook link. Nothing in the prompts, skills or alerts
names the repo, the PR or the change. On a live page the metric value is
the lag measured when the page goes out
([`lag_alert.py`](../harness/pagerduty/lag_alert.py)); the fixture's own
figure is what stub mode serves.

| Fact | How the agent gets it |
|---|---|
| The topic and consumer group | The alert's tags, confirmed through Lenses MCP |
| The downstream impact (`cards.ledger.posted.v1` stops) | Lenses MCP: the service's output topic and its message rate |
| The breaking v2 schema, compatibility `NONE` | Lenses MCP: the subject's versions and config |
| Which repo owns the change, and the culprit PR | GitHub: PRs merged in the org before the incident, then their diffs |
| Why CI didn't catch it | GitHub: the culprit's check runs (the shared schema-compatibility job has been disabled for months) |
| What the runbook gets wrong | Confluence: the runbook is stale on purpose (it still names the consumer group's old name and says to scale out) |

The org around the culprit is noisy on purpose: decoy PRs merged the same
morning touch the paged service, the same topics and ACLs, so "most recent
PR" is the wrong answer. See [The DSS26 Bank GitHub org](github-org.md).

## How a scenario becomes real

The induce script doesn't fake the cause. It merges the culprit PR (on
GitHub in live mode), then
[`harness/github_org/gitops.py`](../harness/github_org/gitops.py) applies
what `main` now says to the cluster, the way the bank's release pipeline
would: the schema and compatibility from merchant-gateway's pom. Reset
merges a revert and applies `main` again. In stub mode, or when GitHub can't
be written to, the same files are applied from the local declarations: the
cluster still breaks, and the stub serves a snapshot in which the culprit
merged minutes before the incident.

## The cluster

One single-broker Kafka cluster, `cards-prod-euw1`
([fast-data-dev](https://github.com/lensesio/fast-data-dev): broker, Schema
Registry and Kafka Connect), managed by Lenses. It carries a cards-platform
catalogue of 32 topics with Avro schemas, descriptions and tags, so the
agent investigates something that looks like a bank's estate rather than a
two-topic toy:

- **Live:** `cards.authorisation.requested.v1` (card authorisations,
  produced by kafka-connect-datagen) and `cards.ledger.posted.v1` (postings
  produced by the fraud-decisioning engine).
- **Catalogue only:** 30 more topics across authorisation, clearing,
  disputes, card lifecycle, fraud, AML and ledger, with schemas and metadata
  but no data.

[`harness/seed/demo_topics.py`](../harness/seed/demo_topics.py) is the
source of truth for every topic. The `seeder` container creates the topics
and schemas, applies the metadata in Lenses and starts the datagen producer
on every `make up`; it is idempotent.
