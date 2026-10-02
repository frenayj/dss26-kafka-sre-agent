# Scenarios

Each folder is one incident the demo can stage on the cluster. There is one
today, [`consumer-lag`](consumer-lag): a merchant-gateway PR registers an
incompatible schema and the fraud-decisioning consumer wedges. See
[The incident](../../docs/scenarios.md) for what breaks and what the agent
has to find.

| File | What it holds | Read by |
|---|---|---|
| `scenario.json` | `title`, `summary`, `page_delay_s` | the Makefile, the operator console |
| `incident.json` | The alert, as PagerDuty returns an incident a Datadog monitor raised | the PagerDuty stub, `make page`, `make run` |
| `induce.sh` | Breaks the cluster, and merges the culprit PR when the GitHub side is on | `make induce`, `make live` |
| `reset.sh` | Restores the cluster and reverts the culprit; idempotent | `make reset`, which runs every scenario's |

```sh
make scenarios                      # list them
make induce SCENARIO=consumer-lag   # break the cluster, then press Run in the dashboard
make live SCENARIO=consumer-lag     # reset, resolve old pages, induce, wait, page PagerDuty
make run SCENARIO=consumer-lag      # run the agent on the alert from the terminal
make reset
```

`SCENARIO` defaults to `consumer-lag`. The operator console shows three
buttons per scenario: the full live run, the break, and the page.

## Adding a scenario

1. **Copy the folder**: `cp -R harness/scenarios/consumer-lag harness/scenarios/<name>`.
2. **`incident.json`**: give it a new incident `id` and `title`, and put in
   `custom_details` only what the monitor would know: the monitor, the
   metric against its threshold, its tags (cluster, consumer group or
   connector, topic, service, team) and a runbook link. `service.name` is the
   PagerDuty service the alert is routed to; `make pd-setup` creates one per
   service the incidents name. A live page of a `kafka.consumer_lag` alert
   replaces `metric_value` with the lag measured on the cluster
   ([`../pagerduty/lag_alert.py`](../pagerduty/lag_alert.py)). Keep the
   threshold in step with the knowledge base and the monitor in the GitHub
   org; `tests/test_lag_alert.py` checks.
3. **`induce.sh` and `reset.sh`**: break the cluster and restore it. Load the
   env files the way the existing scripts do, so they behave the same from
   `make` and from the console. Keep `reset.sh` idempotent: every live run
   starts by resetting every scenario.
4. **`scenario.json`**: a title, a one-line summary, and `page_delay_s`, the
   time from the break until the symptom is real. Paging sooner sends the
   agent to a cluster that still looks healthy.
5. **If the break needs something new on the cluster** (a service to fail, a
   connector, a schema), add it to [`../stack/`](../stack) and its seeding to
   [`../seed/`](../seed).
6. **For forensics to have something to find**, declare the culprit PR (and
   decoys merged the same morning) in the fictional GitHub org under the same
   name: add it to `SCENARIOS` in
   [`../github_org/model.py`](../github_org/model.py) and a `ScenarioPR` to a
   repo module. Call `scenario.py culprit <name>` from `induce.sh` and
   `scenario.py revert <name>` from `reset.sh`, as `consumer-lag` does, then
   `make gh-validate gh-snapshot`.
7. **Optional**: a runbook in the stub knowledge base
   ([`../stubs/_kb_pages.py`](../stubs/_kb_pages.py)) for the alert's
   `runbook_url`, and a walkthrough on the dashboard's architecture page
   ([`ui/src/components/architecture/scenarios.ts`](../../ui/src/components/architecture/scenarios.ts)).

The operator console and the PagerDuty stub pick a new folder up when they
restart. The agent needs no change: nothing in its prompts or skills names a
scenario, a repo or a culprit.
