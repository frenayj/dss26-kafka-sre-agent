# agent/

The Kafka SRE agent: a Strands supervisor and four sub-agents, their prompts
and skills, the MCP servers and clients they use, and the API server behind
the dashboard. This folder is what you would deploy; everything that exists
only to demo or test it is in [`harness/`](../harness), and nothing here
imports from there. [How it works](../docs/architecture.md) explains the
design; this is a map.

| Path | What it is |
|---|---|
| `server.py` | FastAPI app (:8765): incident queue, runs executed as background tasks (`POST /runs`), their frames as server-sent events (`GET /runs/{id}/events`), run history, the model per role (`GET`/`PATCH /models`) |
| `cli.py` | Run one incident from the terminal: `python -m agent.cli incident.json` |
| `runner.py` | Shared core: opens the MCP clients and builds the supervisor for a run |
| `sub_agents/` | One builder per agent. `supervisor.py` wraps the four sub-agents as `@tool`s, composes the reporter's case file, and reports each sub-agent's handoff (its exact prompt, system prompt, tools, model and earlier turns) to the dashboard |
| `prompts/` | One Markdown system prompt per agent, rendered with flags for the tools a run has |
| `skills/` | Kafka skills (`SKILL.md` playbooks) loaded on demand through Strands' `AgentSkills` |
| `mcp_clients.py` | Which MCP server each integration talks to: the vendor's, this agent's own, or (stub mode) the harness's test double |
| `mcp_servers/` | The agent's own Confluence and Slack MCP servers, with guardrails around the vendor APIs |
| `integrations/` | Vendor API clients: Confluence and Slack (behind `mcp_servers/`) and the PagerDuty incident poller |
| `pagerduty_guard.py` | Lets live PagerDuty acknowledge and annotate, nothing else |
| `tool_budget.py` | Hard cap on a sub-agent's tool calls per invocation (forensics) |
| `models.py` | Every agent's model: the LiteLLM gateway, addressed by alias |
| `gateway/litellm.yaml` | The gateway's alias-to-model map, with prompt caching on the Claude aliases |
| `config.py` | Settings from the environment (`.env.sample` documents them) |
| `lenses_oauth.py` | Interactive OAuth login to Lenses MCP, when there is no service-account key |
| `tracing.py` | OpenTelemetry export to Phoenix, one trace per run |
| `run_store.py` | SQLite run history (`logs/runs.db`, `/data/runs.db` in the container) |
| `skills_registry.py`, `mcp_registry.py` | What the dashboard's skill and server toggles list |
| `Dockerfile` | The agent server image, with GitHub's official MCP server baked in (checksum-verified) |

Run it on the host against the compose stack:

```sh
make venv
.venv/bin/python -m agent.server   # stop the agent-server container first
make run                           # or one run in the terminal, on a scenario's alert
```
