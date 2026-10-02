// REST client for the operator console server (harness/ops/ops_server.py, started
// with `make ops`). It runs on the host, polls every status source on its own
// cadence, and runs the demo's make targets one at a time.

import type { IncidentSummary, RunSummary } from "@/lib/api"

export const OPS_BASE: string =
  (import.meta.env.VITE_OPS_BASE as string | undefined) ?? "http://localhost:8770"

// ---------------------------------------------------------------------------
// GET /status
// ---------------------------------------------------------------------------

/** One status source. A failed check replaces the data with its error, so the
 *  fields only exist while ``error`` is null. */
export type OpsSection<T> = { checked_at: number } & (
  | (T & { error: null })
  | { error: string }
)

export interface OpsContainer {
  name: string
  service: string
  /** docker's state: "running" | "exited" | "restarting" | ... */
  state: string
  /** docker's text, e.g. "Up 3 minutes (healthy)", "Exited (0) 2 hours ago". */
  status: string
  health: "healthy" | "unhealthy" | "starting" | null
  /** create-configs, seeder: fine once exited with code 0. */
  one_shot: boolean
}

export interface OpsStack {
  containers: OpsContainer[]
}

export interface OpsConsumer {
  group: string
  lag: number
  active: boolean
}

export interface OpsSchema {
  subject: string
  version: number
  id: number
  /** "NONE" while the consumer-lag incident is live. */
  compatibility: string
}

export interface OpsConnector {
  name: string
  state: string | null
  tasks: string[]
  /** First line of a failed task's trace. */
  error: string | null
}

export interface OpsConnectors {
  connectors: OpsConnector[]
}

export interface OpsAgent {
  incidents: IncidentSummary[]
  last_run: RunSummary | null
}

export interface OpsPagerDutyIncident {
  id: string
  status: "triggered" | "acknowledged"
  title: string | null
  url: string | null
  created_at: string | null
}

export interface OpsPagerDuty {
  /** False without a PagerDuty key: the demo pages the stub instead. */
  enabled: boolean
  incidents: OpsPagerDutyIncident[]
}

export interface OpsCulprit {
  /** The scenario id, e.g. "consumer-lag". */
  scenario: string
  repo: string
  title: string
  /** applied = merged on main (incident live), pending = not merged. */
  state: "applied" | "pending" | "conflict"
}

export interface OpsGitHub {
  /** False when GitHub scenarios are off: the agent reads a snapshot. */
  enabled: boolean
  culprits: OpsCulprit[]
}

/** Each section is absent until its first check lands (a few seconds after
 *  the server starts). */
export interface OpsStatus {
  updated_at: number
  stack?: OpsSection<OpsStack>
  consumer?: OpsSection<OpsConsumer>
  schema?: OpsSection<OpsSchema>
  connectors?: OpsSection<OpsConnectors>
  agent?: OpsSection<OpsAgent>
  pagerduty?: OpsSection<OpsPagerDuty>
  github?: OpsSection<OpsGitHub>
}

// ---------------------------------------------------------------------------
// Actions and jobs
// ---------------------------------------------------------------------------

export type OpsActionGroup = "live" | "steps" | "prepare"

export interface OpsAction {
  /** Unique id, e.g. "live-consumer-lag". */
  name: string
  label: string
  group: OpsActionGroup
  /** What it does (live, induce, page, reset...), for the button's icon. */
  kind: string
  description: string
  /** The make target and its arguments, e.g. ["live", "SCENARIO=consumer-lag"]. */
  make: string[]
  /** Pages a human, so the UI asks first. */
  confirm: boolean
}

export type OpsJobStatus = "running" | "succeeded" | "failed" | "stopped"

export interface OpsJob {
  id: number
  action: string
  label: string
  status: OpsJobStatus
  exit_code: number | null
  started_at: number
  ended_at: number | null
}

export interface OpsJobResponse {
  job: OpsJob | null
  /** Output lines from the requested index on. */
  lines: string[]
  /** The index to ask for next. */
  next: number
}

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

// Long enough for a busy host, short enough that a wedged request never
// holds up the next poll for long.
const TIMEOUT_MS = 5_000

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${OPS_BASE}${path}`, {
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`)
  return (await res.json()) as T
}

/** POST an empty JSON body. The server requires the JSON content type (it
 *  forces a CORS preflight, which only the dashboard's origins pass). */
async function postJson(path: string): Promise<Response> {
  return fetch(`${OPS_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
}

export const fetchOpsStatus = () => getJson<OpsStatus>("/status")

export const fetchOpsActions = () =>
  getJson<{ actions: OpsAction[] }>("/actions").then((res) => res.actions)

export const fetchOpsJob = (after: number) =>
  getJson<OpsJobResponse>(`/job?after=${after}`)

/** Start a make target. Rejects with the server's message on 409 (another
 *  job is running), 404 (unknown action) or any other failure. */
export async function startOpsAction(name: string): Promise<OpsJob> {
  const res = await postJson(`/actions/${encodeURIComponent(name)}`)
  const body = (await res.json().catch(() => ({}))) as { job?: OpsJob; error?: string }
  if (!res.ok || !body.job) {
    throw new Error(body.error ?? `POST /actions/${name} -> ${res.status}`)
  }
  return body.job
}

/** Stop the running job. Resolves false when nothing was running (409). */
export async function stopOpsJob(): Promise<boolean> {
  const res = await postJson("/job/stop")
  if (res.status === 409) return false
  if (!res.ok) throw new Error(`POST /job/stop -> ${res.status}`)
  return true
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/** Milliseconds -> "42s" / "3m 07s" / "1h 02m". */
export function formatDuration(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000))
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${String(sec % 60).padStart(2, "0")}s`
  return `${Math.floor(min / 60)}h ${String(min % 60).padStart(2, "0")}m`
}
