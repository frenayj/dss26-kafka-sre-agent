// Event types emitted by the FastAPI /run SSE endpoint. See agent/server.py
// _translate() for the producer side - these mirror it 1:1.

/** "supervisor" or a sub-agent closure name: triage_agent, kafka_diagnosis_agent, code_forensics_agent, reporter_agent. */
export type Source = string

export interface StartEvent {
  kind: "start"
  preset: string
  /** Id of the incident (from the queue) the run was started on. */
  incident_id: string
  /** Role -> gateway alias the run used (absent on older runs). */
  models?: Record<string, string>
  /** Replay only: the run is still executing, so the stream keeps
   *  delivering its new frames until it ends. */
  following?: boolean
  at: number
}

export interface TextEvent {
  kind: "text"
  source: Source
  delta: string
  at: number
}

export interface ReasoningEvent {
  kind: "reasoning"
  source: Source
  delta: string
  at: number
}

export interface ToolEvent {
  kind: "tool"
  source: Source
  id: string // namespaced: `${source}:${toolUseId}`
  name: string
  input: unknown
  at: number
}

export interface ToolResultEvent {
  kind: "tool_result"
  source: Source
  id: string
  content: string
  status: "success" | "error"
  at: number
}

/** What an agent starts a call with, sent as it starts: the exact prompt it
 *  received plus the rest of its context. The supervisor gets one at the top
 *  of the run (``callId`` null); each sub-agent call gets one carrying the
 *  supervisor's tool call id. Absent on runs recorded before it existed. */
export interface HandoffEvent {
  kind: "handoff"
  source: Source
  callId: string | null
  prompt: string
  systemPrompt: string
  tools: string[]
  /** Gateway alias, e.g. "claude-haiku". */
  model: string | null
  /** Messages it already holds from earlier calls in the run. */
  priorMessages: number
  at: number
}

export interface AssistantDoneEvent {
  kind: "assistant_done"
  source: Source
  at: number
}

export interface DoneEvent {
  kind: "done"
  at: number
}

export interface AgentErrorEvent {
  kind: "agent_error"
  message: string
  type: string
  at: number
}

export interface MetricsEvent {
  kind: "metrics"
  source: Source
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cacheReadTokens?: number
  cacheWriteTokens?: number
  latencyMs: number
  cycles?: number
  at: number
}

/** Per-LLM-call usage. Emitted as Strands streams each assistant message,
 *  so the UI can show live token totals before the supervisor or
 *  sub-agent terminates. Client reducer accumulates these per source,
 *  then replaces the running total when the authoritative `metrics`
 *  event arrives at the end of the agent's stream. */
export interface MetricsDeltaEvent {
  kind: "metrics_delta"
  source: Source
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cacheReadTokens?: number
  cacheWriteTokens?: number
  at: number
}

/** Per-source aggregate. Values come from Strands' EventLoopMetrics - the
 *  same numbers the agent exports to its OpenTelemetry traces (Phoenix). */
/** One model call's tokens. ``inputTokens`` is the whole prompt, cached
 *  reads and writes included. */
export interface CallUsage {
  inputTokens: number
  outputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
}

export interface AgentMetrics {
  source: Source
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cacheReadTokens?: number
  cacheWriteTokens?: number
  latencyMs: number
  cycles?: number
  /** Each model call, from ``metrics_delta``: a model priced by prompt
   *  length is priced call by call. */
  calls?: CallUsage[]
}

export type RunEvent =
  | StartEvent
  | TextEvent
  | ReasoningEvent
  | ToolEvent
  | ToolResultEvent
  | HandoffEvent
  | AssistantDoneEvent
  | DoneEvent
  | AgentErrorEvent
  | MetricsEvent
  | MetricsDeltaEvent

/** Lifecycle of a single tool invocation. Accumulates streaming input. */
export interface ToolCall {
  id: string
  source: Source
  name: string
  input: unknown
  result?: string
  status: "pending" | "success" | "error"
  startedAt: number
  completedAt?: number
}

/** Rows the chat feed renders, in order of arrival. */
export type Row =
  | {
      kind: "text"
      id: string
      source: Source
      content: string // coalesced
      startedAt: number
    }
  | {
      kind: "reasoning"
      id: string
      source: Source
      content: string // coalesced
      startedAt: number
    }
  | {
      kind: "tool"
      id: string
      source: Source
      toolCallId: string
      startedAt: number
    }
  | {
      kind: "error"
      id: string
      message: string
      type: string
      startedAt: number
    }

export type StreamStatus = "idle" | "running" | "done" | "error"

export type StreamMode = "live" | "replay"

export interface StreamState {
  events: RunEvent[]
  rows: Row[]
  toolCalls: Map<string, ToolCall>
  agentMetrics: Map<Source, AgentMetrics>
  status: StreamStatus
  mode: StreamMode
  runId?: string
  /** Replay of a run still in progress - see StartEvent.following. */
  following?: boolean
  error?: { message: string; type: string }
  startedAt?: number
  endedAt?: number
}
