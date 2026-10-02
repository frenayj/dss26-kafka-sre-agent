// Tiny REST client for the FastAPI side. The /run endpoint is SSE - that's
// handled separately in hooks/useRunStream.ts.

export const AGENT_BASE: string =
  (import.meta.env.VITE_AGENT_BASE as string | undefined) ?? "http://localhost:8765"

export interface PingResponse {
  /** "healthy" once FastAPI has fully started; "needs_auth" while the
   *  temporary OAuth callback handler is holding port 8765 waiting for
   *  the user to sign in to Lenses HQ. */
  status: "healthy" | "needs_auth" | string
  tools: Record<string, unknown>
  /** Present only when status === "needs_auth". The URL the user must open
   *  to complete the Lenses OAuth flow. */
  auth_url?: string | null
}

export interface PresetsResponse {
  presets: Record<string, string>
}

export interface SkillInfo {
  name: string
  description: string
}

export interface SkillsResponse {
  skills: SkillInfo[]
}

export interface McpServerInfo {
  name: string
  description: string
  sub_agent: string
  tool_count: number
}

export interface McpServersResponse {
  servers: McpServerInfo[]
}

export type IncidentStatus = "pending" | "in_progress" | "completed"

/** Row returned by GET /incidents - light, for list rendering. */
export interface IncidentSummary {
  id: string
  created_at: number
  title: string | null
  severity: string | null
  service: string | null
  status: IncidentStatus
  last_run_id: string | null
  /** Live PagerDuty only: a fresh page nobody has run yet. The dashboard
   *  claims it (claimIncident) and starts the run on its own. */
  auto_run?: boolean
}

/** Row returned by GET /incidents/:id - includes the full payload. */
export interface IncidentDetail extends IncidentSummary {
  payload: unknown
}

export interface IncidentsResponse {
  incidents: IncidentSummary[]
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${AGENT_BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`)
  return (await res.json()) as T
}

export const fetchPing = () => getJson<PingResponse>("/ping")
export const fetchPresets = () => getJson<PresetsResponse>("/presets")
export const fetchSkills = () => getJson<SkillsResponse>("/skills")
export const fetchMcpServers = () => getJson<McpServersResponse>("/mcp_servers")

export const fetchIncidents = (limit = 100) =>
  getJson<IncidentsResponse>(`/incidents?limit=${limit}`)

export const fetchIncident = (id: string) =>
  getJson<IncidentDetail>(`/incidents/${encodeURIComponent(id)}`)

/** Claim an ``auto_run`` incident. Resolves false when another dashboard got
 *  there first (409), so only one browser tab runs each page. */
export async function claimIncident(id: string): Promise<boolean> {
  const res = await fetch(`${AGENT_BASE}/incidents/${encodeURIComponent(id)}/claim`, {
    method: "POST",
  })
  if (res.status === 409) return false
  if (!res.ok) throw new Error(`POST /incidents/${id}/claim -> ${res.status}`)
  return true
}

// Gateway model aliases (must match `model_name` in agent/gateway/litellm.yaml).
// The selector picks one of these per role; the backend forwards it verbatim as the OpenAI `model` field and the
// LiteLLM gateway routes it to the underlying provider.
export type ModelAlias =
  | "claude"
  | "claude-haiku-5-5"
  | "claude-haiku"
  | "mistral-medium"
  | "mistral-large"
  | "gpt"

export type AgentRole =
  | "supervisor"
  | "triage"
  | "diagnosis"
  | "forensics"
  | "reporter"

export type ModelSelection = Partial<Record<AgentRole, ModelAlias>>

// Per-role defaults: every role starts on the `claude` alias, matching the
// backend's *_MODEL defaults in agent/config.py. Prices runs stored before
// the start frame named its models.
export const DEFAULT_MODELS: Record<AgentRole, ModelAlias> = {
  supervisor: "claude",
  triage: "claude",
  diagnosis: "claude",
  forensics: "claude",
  reporter: "claude",
}

/** The alias each role runs on: one setting on the server, shared by every
 *  dashboard and the operator console. The next run uses it. */
export async function fetchModels(): Promise<ModelSelection> {
  const res = await fetch(`${AGENT_BASE}/models`)
  if (!res.ok) throw new Error(`GET /models -> ${res.status}`)
  return ((await res.json()) as { models: ModelSelection }).models
}

/** Point one role at another alias; answers the whole setting. */
export async function updateModel(role: AgentRole, alias: ModelAlias): Promise<ModelSelection> {
  const res = await fetch(`${AGENT_BASE}/models`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ [role]: alias }),
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: string } | null
    throw new Error(body?.error ?? `PATCH /models -> ${res.status}`)
  }
  return ((await res.json()) as { models: ModelSelection }).models
}

/** Start a run on the server and return its id. The run executes there,
 *  independently of this page; follow it with ``runEventsUrl``. Omitting
 *  ``enabledSkills`` / ``enabledServers`` means all of them; an empty list
 *  means none. The run uses the server's models (``fetchModels``). */
export async function createRun(
  preset: string,
  incidentId: string,
  enabledSkills?: string[],
  enabledServers?: string[],
): Promise<string> {
  const res = await fetch(`${AGENT_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      preset,
      incident_id: incidentId,
      skills: enabledSkills,
      servers: enabledServers,
    }),
  })
  if (!res.ok) throw new Error(`POST /runs -> ${res.status}`)
  const body = (await res.json()) as { run_id: string }
  return body.run_id
}

/** Stop a run that is executing. A run that already ended answers 409. */
export async function cancelRun(runId: string): Promise<void> {
  const res = await fetch(`${AGENT_BASE}/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
  })
  if (!res.ok && res.status !== 409) throw new Error(`cancel ${runId} -> ${res.status}`)
}

/** SSE stream of a run's frames: followed while it executes, replayed after. */
export function runEventsUrl(runId: string): string {
  return `${AGENT_BASE}/runs/${encodeURIComponent(runId)}/events`
}

export interface RunSummary {
  id: string
  preset: string
  incident_id: string
  status: "running" | "done" | "error" | "cancelled"
  started_at: number
  ended_at: number | null
  error_type: string | null
  error_message: string | null
  tool_call_count: number
  input_tokens: number
  output_tokens: number
  latency_ms: number
  /** User-facing display name. Defaults to the incident title at run creation;
   *  the user can rename via PATCH /runs/{id}. Null = fall back to incident_id. */
  name: string | null
}

export interface RunsResponse {
  runs: RunSummary[]
}

export const fetchRuns = (limit = 50) =>
  getJson<RunsResponse>(`/runs?limit=${limit}`)

export async function deleteRun(id: string): Promise<void> {
  const res = await fetch(`${AGENT_BASE}/runs/${encodeURIComponent(id)}`, {
    method: "DELETE",
  })
  if (!res.ok) throw new Error(`DELETE /runs/${id} -> ${res.status}`)
}

export async function updateRunName(id: string, name: string | null): Promise<RunSummary> {
  const res = await fetch(`${AGENT_BASE}/runs/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`PATCH /runs/${id} -> ${res.status}`)
  return (await res.json()) as RunSummary
}
