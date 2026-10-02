# Going live: real PagerDuty, GitHub, Confluence and Slack

By default the four non-Lenses integrations serve bundled fixtures, so the
demo runs offline and needs no accounts. Each one can be switched to the
real vendor on its own:

| Server | Mode variable | Live back-end | Credentials |
|---|---|---|---|
| PagerDuty | `PAGERDUTY_MODE` | PagerDuty's hosted MCP server, plus an incident poller | `PAGERDUTY_API_KEY` (a user API token) |
| GitHub | `GITHUB_MODE` | GitHub's official MCP server, read-only | `GITHUB_TOKEN` |
| Confluence | `CONFLUENCE_MODE` | Confluence Cloud REST API (reads the knowledge base, publishes the RCA) | `CONFLUENCE_BASE_URL`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN` |
| Slack | `SLACK_MODE` | Web API `chat.postMessage` | `SLACK_BOT_TOKEN` |

Every mode defaults to `stub`, and anything other than `live` means `stub`,
so a typo never talks to a vendor.

## Switching a server to live

1. Get a credential (each section below says how).
2. In `.env`, set `<NAME>_MODE=live` and the credential variables.
   [`.env.sample`](../.env.sample) lists them all.
3. `make agent-up`. This recreates the agent server, because compose only
   reads `.env` when it creates a container; a `docker restart` keeps the
   old values. (Running the agent on the host instead? Just restart it.)
4. Check the dashboard's MCP server list: each row is labelled from its
   actual mode (*Live GitHub* rather than *Simulated GitHub*), plus
   *[dry run]* on Confluence and Slack until you arm them.

Switch one server at a time. To go back, set the mode to `stub` and
`make agent-up` again.

## PagerDuty

Live PagerDuty changes how a run starts, not just where data comes from:

1. `make page` sends the scenario's Datadog-style alert to PagerDuty's
   Events API. PagerDuty opens a P1 incident and pages
   whoever is on call. The alert's lag is not the fixture's: `page` reads
   the consumer group's lag on the cluster, waits for it to pass the
   monitor's threshold (5,000) and sends that figure, so the alert agrees
   with what Lenses shows the agent.
2. The agent server polls PagerDuty every `PAGERDUTY_POLL_S` seconds (5 by
   default) and adds new open incidents to the dashboard. Polling needs no
   inbound route, so it works on any network without a tunnel.
3. When an incident arrives still `triggered`, the open dashboard claims it
   and starts the run on its own. If several dashboards are open, only one
   wins the claim.
4. Triage connects to PagerDuty's hosted MCP server
   (`https://mcp.pagerduty.com/mcp`). It acknowledges the incident, reads it
   and its alerts, and adds a note. The reporter adds a closing note with
   the root cause, the next step and the RCA link.
5. You resolve the incident yourself, in PagerDuty.

The agent gets two of the hosted server's tools, `browse_incidents` and
`manage_incidents`, and a hook
([`agent/pagerduty_guard.py`](../agent/pagerduty_guard.py)) cancels every
`manage_incidents` call except acknowledge and add-note. The agent cannot
resolve, reassign, escalate or page anyone else.

**Get a token.** In PagerDuty: **My Profile → User Settings → Create API User
Token**. It must be a *user* token: the MCP server expects one, and the
agent's notes appear under that user's name.

**Set up the account** (idempotent, works on a new account):

```sh
PAGERDUTY_API_KEY=<user token> make pd-setup
```

This creates one service per service the scenarios' alerts name (today
`fraud-decisioning-svc`) on your first escalation policy, adds an Events API
integration to each, and adds an orchestration rule that marks their events
P1 (the Events API can't set priority). It prints the service ids:

```bash
PAGERDUTY_MODE=live
PAGERDUTY_API_KEY=<user token>
PAGERDUTY_SERVICE_IDS=<ids printed by make pd-setup>
# EU accounts:
# PAGERDUTY_API_URL=https://api.eu.pagerduty.com
# PAGERDUTY_MCP_URL=https://mcp.eu.pagerduty.com/mcp
```

**Run it:**

```sh
make live   # reset -> resolve old pages -> induce -> wait 45s -> page
```

It's also the first button in the
[operator console](scenarios.md#the-operator-console), and takes
`SCENARIO=<name>` like the other scenario targets. The wait (the scenario's
`page_delay_s`, or `PAGE_DELAY_S` to override it) gives the consumer time to
stall, so the agent finds real, growing lag. Keep a dashboard open before you page: it claims the
incident and starts the run, on the models set in the operator console or
the dashboard's Models panel (one setting, held by the agent server). The run then executes on the server, so you
can switch to `#/ops` or `#/pagerduty`, reload or close the tab without
stopping it; every dashboard you open follows it, and **Stop** cancels it.
`make pd-resolve` resolves every open incident on the demo services.

In live mode the dashboard shows only real incidents; the bundled one
doesn't exist on your account. The poller folds the alert's Datadog details
onto the incident, so the supervisor receives the same payload shape as in
stub mode.

## GitHub

Live GitHub is GitHub's official MCP server
([`github/github-mcp-server`](https://github.com/github/github-mcp-server),
pinned and baked into the agent image), started with `--read-only` and an
8-tool allowlist: `search_pull_requests`, `list_pull_requests`,
`pull_request_read`, `search_code`, `get_file_contents`, `list_commits`,
`get_commit`, `search_repositories`. The stub serves the same tools over a
snapshot of the same org, so the forensics prompt and the UI don't change.

**Get a token.** **Settings → Developer settings → Personal access tokens →
Fine-grained tokens**. Resource owner: the org. Repository access: all
repositories. Permissions: **Contents: read** and **Pull requests: read**.
(Fine-grained tokens can't read check runs, so `get_check_runs` answers 403
and forensics says so; a classic token with `repo` scope can.)

```bash
GITHUB_MODE=live
GITHUB_TOKEN=<token>
GITHUB_ORG=dss26-org                # the org to investigate
# GITHUB_API_URL=https://ghe.example.com/api/v3   # GitHub Enterprise Server
```

The agent image ships the server binary. To run the agent on the host with
live GitHub, put `github-mcp-server` on your PATH, or set `GITHUB_MCP_COMMAND`
to the `docker run` command from the server's README.

The forensics agent is told the org name and nothing else. Runs against
GitHub need an org with the scenario's history in it: see
[The DSS26 Bank GitHub org](github-org.md) to create your own copy.

## Confluence

Confluence is both the team's knowledge base (triage reads the runbook the
alert links to; the reporter looks up the standards the root cause touches
and flags pages the evidence contradicts) and where the RCA is published.

**Get a token.** Confluence **Cloud** only. At
[id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens):
**Security → Create and manage API tokens → Create API token** (the plain
one, not *with scopes*). The account needs permission to add pages in the
target space.

```bash
CONFLUENCE_MODE=live
CONFLUENCE_BASE_URL=https://your-site.atlassian.net/wiki
CONFLUENCE_EMAIL=you@example.com
CONFLUENCE_API_TOKEN=<token>
CONFLUENCE_SPACE=SRE                # space to search and publish in
CONFLUENCE_PARENT_PAGE_ID=<id>      # optional: file RCAs under this page
# CONFLUENCE_DRY_RUN=false          # only once you want pages created
```

**Check it** while dry run is still on (otherwise this creates a page):

```sh
docker exec dss26-agent-server-1 python -c \
  "from agent.integrations import confluence as cf; print(cf.create_page('SRE', 'connectivity check', 'test'))"
```

A `"dry_run": true` answer means the credential works and the space
resolved. Then set `CONFLUENCE_DRY_RUN=false` and `make agent-up`.

**Guardrails.** `CONFLUENCE_SPACE` overrides the space the model asks for
and also scopes the knowledge-base search. A page whose title already exists
comes back as `deduplicated`, so a retried run doesn't fail on Confluence's
duplicate-title error. The reporter writes Markdown, which is rendered to
Confluence storage format with raw HTML escaped.

The knowledge base the stub serves
([`harness/stubs/_kb_pages.py`](../harness/stubs/_kb_pages.py), 29 pages, some
stale on purpose) also exists as a real space the talk uses. Your site won't
have those pages, so live runs against your own space read whatever it holds.

## Slack

**Get a token.** The app is defined by
[`agent/integrations/slack-app-manifest.yaml`](../agent/integrations/slack-app-manifest.yaml). At
[api.slack.com/apps](https://api.slack.com/apps): **Create New App → From a
manifest**, pick the workspace, paste the file and create it. **Install to
Workspace**, then copy the **Bot User OAuth Token** (`xoxb-…`). The manifest
grants `chat:write` only, so invite the bot to the channel
(`/invite @kafka-sre-agent`), or uncomment `chat:write.public` before
creating the app.

```bash
SLACK_MODE=live
SLACK_BOT_TOKEN=xoxb-...
SLACK_DEFAULT_CHANNEL=#sre-agent-sandbox   # or SLACK_CHANNEL_ALLOWLIST=a,b
# SLACK_DRY_RUN=false                      # only once you want it to post
```

**Check it** while dry run is still on:

```sh
docker exec dss26-agent-server-1 python -c \
  "from agent.integrations import slack as sl; print(sl.post_message('#sre-agent-sandbox', 'connectivity check'))"
```

**Guardrails.**

1. **Channel policy.** `SLACK_DEFAULT_CHANNEL` pins every post to one
   channel, whatever the model asks for; `SLACK_CHANNEL_ALLOWLIST` lets it
   choose from a fixed set. Set one of them: the reporter's default channel,
   `#sre-oncall`, probably doesn't exist in your workspace.
2. **Dry run by default.** A post can't be taken back, so arming it is a
   second, deliberate step. A dry run still calls `auth.test`, so it proves
   the token and workspace.
3. **Dedupe.** Slack has no idempotency key, and both the agent loop and the
   gateway retry. An on-disk ledger suppresses an identical
   `(channel, text)` within `SLACK_DEDUPE_TTL_S`. It keys on exact text, so
   dry run remains the real protection.

The tool's answer says which of the three happened: `ts` (posted),
`dry_run` (checked, not sent) or `deduplicated` (already posted).
