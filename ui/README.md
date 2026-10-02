# Kafka SRE Agent dashboard

React + Vite front end for the Kafka SRE agent. Pick an incident, start a run,
and watch the supervisor and its sub-agents work: a live activity feed with a
rendered result for each tool call, a timeline, token usage, and replayable
run history. It talks to the agent server (`agent/server.py`) over REST and
Server-Sent Events.

## Development

```sh
pnpm install
pnpm dev      # http://localhost:5173
pnpm build    # type-check (tsc -b) + production build into dist/
pnpm lint
```

`pnpm dev` expects the agent server on `http://localhost:8765`. Requests go to
`VITE_AGENT_BASE` (default `http://localhost:8765`). If the agent runs in
Docker, whose CORS allowlist only admits the containerised UI, put
`VITE_AGENT_BASE=` (empty) in `.env.local`. Requests then stay relative and go
through the dev proxy in `vite.config.ts`. The Docker image sets
`VITE_AGENT_BASE` at build time (`ui/Dockerfile`).

## Layout

- `src/App.tsx`: the dashboard (sidebar, activity feed, inspector panel)
- `src/hooks/useRunStream.ts`: opens the SSE stream for a live run or a replay and reduces its events into state
- `src/lib/api.ts` / `src/lib/types.ts`: REST client and the SSE event types
- `src/lib/models.ts`: the gateway's model aliases, with the per-token prices used to cost a run
- `src/lib/runSummary.ts`: the end-of-run summary's data: each agent step's measured time and cost, and the on-call team baseline it is compared with (an estimate)
- `src/lib/handoffs.ts`: what passed between the agents, per agent call: the brief, the answer, the context the agent started from and its context window per model call
- `src/components/chat/`: the activity feed (`EventStream`, `ToolCard`)
- `src/components/handoffs/`: the handoff view (`HandoffsDialog`), the context-window charts, and the brief / context / answer blocks on each agent's card
- `src/components/tools/`: one renderer per tool, picked by `ToolResultRouter.tsx`; `kafka/` holds the Lenses MCP ones
- `src/components/layout/`: sidebar sections, right panel, dialogs
- `src/components/architecture/`: graph and scenario data for the architecture explainer
- `src/components/ui/`: shadcn/ui primitives
- `src/pages/`: the hidden pages below

## Hidden pages

None of these pages is linked from the UI. Open them by URL:

- `#/architecture`: interactive architecture diagram with a step-by-step walkthrough of each incident scenario
- `#/pagerduty`: full-screen PagerDuty incident view (`#/pagerduty/<incident-id>` opens a specific incident)
- `#/ops`: operator console with live status, a button per scenario make target and the model per agent; needs `make ops` running (requests go to `VITE_OPS_BASE`, default `http://localhost:8770`)
