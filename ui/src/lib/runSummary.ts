import { DEFAULT_MODELS, type AgentRole } from "@/lib/api"
import { modelInfo, tokenCostUsd } from "@/lib/models"
import type { StreamState } from "@/lib/types"

/**
 * The data behind the end-of-run summary: the same incident handled by a
 * human on-call team (an estimate) and by the agent (measured on the run).
 * Both end at the same point: root cause identified, RCA published, channel
 * told. Fixing it stays a human decision either way.
 */

/** One step of a response, timed from the moment the alert fires. */
export interface Step {
  key: string
  label: string
  /** Who does it: the people involved, or the model. */
  who: string
  engineers?: number
  /** When the step is running, in ms since the alert. */
  segments: { start: number; end: number }[]
  durationMs: number
  costUsd: number | null
  /** Runs for the whole response rather than as one stage of it. */
  throughout?: boolean
}

export interface Response {
  steps: Step[]
  totalMs: number
  /** Null when part of it can't be priced (a model with no price). */
  costUsd: number | null
}

// ---------------------------------------------------------------------------
// The on-call team: an estimate, and labelled as one wherever it is shown.
// ---------------------------------------------------------------------------

/** Fully loaded cost of an engineer's hour (salary, benefits, overhead). */
export const ENGINEER_USD_PER_HOUR = 150

/** A P1 Kafka incident worked by people: page to published RCA in 95 min,
 *  pulling in up to four engineers. Conservative on purpose: incidents that
 *  cross team boundaries routinely take hours. */
const ONCALL_STEPS: { label: string; who: string; engineers: number; minutes: number }[] = [
  {
    label: "Acknowledge, runbook, dashboards",
    who: "On-call SRE",
    engineers: 1,
    minutes: 20,
  },
  {
    label: "Escalate to Kafka platform",
    who: "On-call + Kafka engineer",
    engineers: 2,
    minutes: 25,
  },
  {
    label: "Incident bridge: find the change",
    who: "+ commander, app engineer",
    engineers: 4,
    minutes: 30,
  },
  {
    label: "Write the RCA, update the channel",
    who: "On-call + commander",
    engineers: 2,
    minutes: 20,
  },
]

const MIN = 60_000

export function oncallResponse(): Response {
  let at = 0
  const steps = ONCALL_STEPS.map((s, i): Step => {
    const start = at
    at += s.minutes * MIN
    return {
      key: `oncall-${i}`,
      label: s.label,
      who: s.who,
      engineers: s.engineers,
      segments: [{ start, end: at }],
      durationMs: s.minutes * MIN,
      costUsd: s.engineers * (s.minutes / 60) * ENGINEER_USD_PER_HOUR,
    }
  })
  return { steps, totalMs: at, costUsd: sum(steps.map((s) => s.costUsd)) }
}

// ---------------------------------------------------------------------------
// The agent: measured on the run.
// ---------------------------------------------------------------------------

/** The supervisor's sub-agent tools, in the order of work. */
const AGENT_STEPS: { source: string; role: AgentRole; label: string }[] = [
  { source: "triage_agent", role: "triage", label: "Triage: alert and runbook" },
  { source: "kafka_diagnosis_agent", role: "diagnosis", label: "Kafka diagnosis (Lenses MCP)" },
  { source: "code_forensics_agent", role: "forensics", label: "Code forensics (GitHub)" },
  { source: "reporter_agent", role: "reporter", label: "Reporter: RCA and Slack" },
]

/**
 * First and last timestamp of the run. Rows and tool calls are stamped from
 * SERVER events (``evt.at``), so they carry the original timing in live and
 * replay alike. ``startedAt``/``endedAt`` are not: ``startedAt`` is the
 * client's clock when the stream opened, so on a replay it is "now" while
 * ``endedAt`` is the original completion time.
 */
function runSpan(state: StreamState): { start: number; end: number } | null {
  const times: number[] = []
  for (const r of state.rows) times.push(r.startedAt)
  for (const tc of state.toolCalls.values()) {
    times.push(tc.startedAt)
    if (tc.completedAt) times.push(tc.completedAt)
  }
  if (times.length >= 2) {
    const start = Math.min(...times)
    const end = Math.max(...times)
    if (end > start) return { start, end }
  }
  if (state.startedAt && state.endedAt && state.endedAt > state.startedAt) {
    return { start: state.startedAt, end: state.endedAt }
  }
  return null
}

/** Role -> alias the run used, from the server's start frame. Runs recorded
 *  before the frame carried it fall back to the defaults. */
function runModels(state: StreamState): Record<string, string> {
  let models: Record<string, string> = { ...DEFAULT_MODELS }
  for (const e of state.events) {
    if (e.kind === "start" && e.models && Object.keys(e.models).length > 0) {
      models = { ...models, ...e.models }
    }
  }
  return models
}

export function agentResponse(state: StreamState): Response | null {
  const span = runSpan(state)
  if (!span) return null
  const totalMs = span.end - span.start
  const models = runModels(state)

  const cost = (source: string, role: AgentRole): number | null => {
    const m = state.agentMetrics.get(source)
    return m ? tokenCostUsd(m, models[role]) : 0
  }
  const who = (role: AgentRole): string => modelInfo(models[role])?.label ?? models[role]

  const steps: Step[] = []
  for (const { source, role, label } of AGENT_STEPS) {
    // A sub-agent can be called more than once (the optional follow-up).
    const segments = [...state.toolCalls.values()]
      .filter((tc) => tc.source === "supervisor" && tc.name === source)
      .map((tc) => ({
        start: tc.startedAt - span.start,
        end: (tc.completedAt ?? span.end) - span.start,
      }))
    if (segments.length === 0) continue
    steps.push({
      key: source,
      label,
      who: who(role),
      segments,
      durationMs: segments.reduce((acc, s) => acc + (s.end - s.start), 0),
      costUsd: cost(source, role),
    })
  }
  steps.push({
    key: "supervisor",
    label: "Supervisor: plans, cross-checks",
    who: who("supervisor"),
    segments: [{ start: 0, end: totalMs }],
    durationMs: totalMs,
    costUsd: cost("supervisor", "supervisor"),
    throughout: true,
  })

  return { steps, totalMs, costUsd: sum(steps.map((s) => s.costUsd)) }
}

function sum(values: (number | null)[]): number | null {
  let total = 0
  for (const v of values) {
    if (v == null) return null
    total += v
  }
  return total
}
