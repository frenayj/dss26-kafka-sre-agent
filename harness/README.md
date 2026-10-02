# harness/

Everything that exists to run, demo and test the agent: a Kafka estate to
break, incidents to stage on it, offline stand-ins for the vendors, and the
tools the presenter uses. The agent itself is in [`agent/`](../agent).

**The boundary.** Nothing in `agent/` imports from here. The agent reaches
the harness the way it would reach a real estate: over MCP and over the
network. In stub mode it spawns the test doubles in `stubs/` instead of the
vendors' MCP servers, and it talks to the cluster, Lenses and the model
gateway that `stack/` runs. Point it at a real estate (every integration
live, Lenses on your cluster) and the agent doesn't change.

| Path | What it is |
|---|---|
| [`stack/`](stack) | The Docker Compose stack. It runs the harness's services (the Kafka cluster `cards-prod-euw1`, Lenses, the fraud-decisioning consumer) and the agent's (agent server, dashboard, LLM gateway, Phoenix), built from `agent/` and `ui/` |
| [`scenarios/`](scenarios) | The incidents, one folder each: the alert, a script that breaks the cluster and one that restores it. How to add one |
| [`stubs/`](stubs) | Offline MCP servers for PagerDuty, GitHub, Confluence and Slack, serving the fictional bank's incidents, org snapshot and knowledge base |
| [`github_org/`](github_org) | The fictional bank's GitHub org, declared as code: seeds a real org and generates the GitHub stub's snapshot |
| [`seed/`](seed) | Seeds the cluster (topics, schemas, Lenses metadata, the datagen producer), mints the Lenses service account, registers model pricing in Phoenix |
| [`pagerduty/`](pagerduty) | Sets up a real PagerDuty account, pages it with a scenario's alert, resolves the pages |
| [`ops/`](ops) | The operator console's server (`make ops`), behind the dashboard's unlisted `#/ops` page |

The presenter pages (`#/ops`, `#/architecture`, `#/pagerduty`) are part of
the dashboard build, in [`ui/src/pages/`](../ui/src/pages); none of them is
linked from the dashboard itself.
