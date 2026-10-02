import { useCallback, useEffect, useReducer, useRef } from "react"
import { cancelRun, createRun, runEventsUrl } from "@/lib/api"
import type {
  RunEvent,
  Row,
  StreamMode,
  StreamState,
  ToolCall,
} from "@/lib/types"

const INITIAL: StreamState = {
  events: [],
  rows: [],
  toolCalls: new Map(),
  agentMetrics: new Map(),
  status: "idle",
  mode: "live",
}

type Action =
  | {
      type: "start"
      mode: StreamMode
      preset: string
      incidentId: string
      runId?: string
      at: number
    }
  | { type: "event"; event: RunEvent }
  | { type: "done"; at: number }
  | { type: "error"; message: string; errorType: string; at: number }
  | { type: "reset" }

function rowId(prefix: string, n: number): string {
  return `${prefix}-${n}`
}

function reduce(state: StreamState, action: Action): StreamState {
  switch (action.type) {
    case "reset":
      return { ...INITIAL, toolCalls: new Map(), agentMetrics: new Map() }

    case "start":
      return {
        ...INITIAL,
        toolCalls: new Map(),
        agentMetrics: new Map(),
        status: "running",
        mode: action.mode,
        runId: action.runId,
        startedAt: action.at,
        events: [
          {
            kind: "start",
            preset: action.preset,
            incident_id: action.incidentId,
            at: action.at,
          },
        ],
      }

    case "done":
      return { ...state, status: "done", endedAt: action.at }

    case "error":
      return {
        ...state,
        status: "error",
        endedAt: action.at,
        error: { message: action.message, type: action.errorType },
      }

    case "event": {
      const evt = action.event
      const events = [...state.events, evt]

      switch (evt.kind) {
        case "text":
        case "reasoning": {
          const last = state.rows[state.rows.length - 1]
          // Coalesce consecutive deltas of the same kind+source into one row.
          if (last && last.kind === evt.kind && last.source === evt.source) {
            const merged: Row = { ...last, content: last.content + evt.delta }
            return { ...state, events, rows: [...state.rows.slice(0, -1), merged] }
          }
          const row: Row = {
            kind: evt.kind,
            id: rowId(evt.kind, state.rows.length),
            source: evt.source,
            content: evt.delta,
            startedAt: evt.at,
          }
          return { ...state, events, rows: [...state.rows, row] }
        }

        case "tool": {
          const toolCalls = new Map(state.toolCalls)
          const existing = toolCalls.get(evt.id)
          const call: ToolCall = existing
            ? { ...existing, name: evt.name, input: evt.input }
            : {
                id: evt.id,
                source: evt.source,
                name: evt.name,
                input: evt.input,
                status: "pending",
                startedAt: evt.at,
              }
          toolCalls.set(evt.id, call)
          // Only push a row the first time we see this tool call.
          if (existing) {
            return { ...state, events, toolCalls }
          }
          const row: Row = {
            kind: "tool",
            id: rowId("tool", state.rows.length),
            source: evt.source,
            toolCallId: evt.id,
            startedAt: evt.at,
          }
          return { ...state, events, rows: [...state.rows, row], toolCalls }
        }

        case "tool_result": {
          const toolCalls = new Map(state.toolCalls)
          const existing = toolCalls.get(evt.id)
          const updated: ToolCall = existing
            ? {
                ...existing,
                result: evt.content,
                status: evt.status,
                completedAt: evt.at,
              }
            : {
                id: evt.id,
                source: evt.source,
                name: "(unknown)",
                input: undefined,
                result: evt.content,
                status: evt.status,
                startedAt: evt.at,
                completedAt: evt.at,
              }
          toolCalls.set(evt.id, updated)
          return { ...state, events, toolCalls }
        }

        case "metrics": {
          // Authoritative final aggregate for this source. Replace any
          // running totals built up from metrics_delta events, keeping their
          // per-call breakdown.
          const agentMetrics = new Map(state.agentMetrics)
          agentMetrics.set(evt.source, {
            source: evt.source,
            inputTokens: evt.inputTokens,
            outputTokens: evt.outputTokens,
            totalTokens: evt.totalTokens,
            cacheReadTokens: evt.cacheReadTokens,
            cacheWriteTokens: evt.cacheWriteTokens,
            latencyMs: evt.latencyMs,
            cycles: evt.cycles,
            calls: state.agentMetrics.get(evt.source)?.calls,
          })
          return { ...state, events, agentMetrics }
        }

        case "metrics_delta": {
          // Per-LLM-call usage. Accumulate into the source's running
          // totals so the UI can show live progress before the agent
          // terminates. The eventual `metrics` event will replace this
          // with the authoritative value (should match within rounding).
          const agentMetrics = new Map(state.agentMetrics)
          const prev = agentMetrics.get(evt.source)
          agentMetrics.set(evt.source, {
            source: evt.source,
            inputTokens: (prev?.inputTokens ?? 0) + evt.inputTokens,
            outputTokens: (prev?.outputTokens ?? 0) + evt.outputTokens,
            totalTokens: (prev?.totalTokens ?? 0) + evt.totalTokens,
            cacheReadTokens:
              (prev?.cacheReadTokens ?? 0) + (evt.cacheReadTokens ?? 0),
            cacheWriteTokens:
              (prev?.cacheWriteTokens ?? 0) + (evt.cacheWriteTokens ?? 0),
            latencyMs: prev?.latencyMs ?? 0,
            cycles: prev?.cycles,
            calls: [
              ...(prev?.calls ?? []),
              {
                inputTokens: evt.inputTokens,
                outputTokens: evt.outputTokens,
                cacheReadTokens: evt.cacheReadTokens ?? 0,
                cacheWriteTokens: evt.cacheWriteTokens ?? 0,
              },
            ],
          })
          return { ...state, events, agentMetrics }
        }

        case "agent_error": {
          const row: Row = {
            kind: "error",
            id: rowId("err", state.rows.length),
            message: evt.message,
            type: evt.type,
            startedAt: evt.at,
          }
          return {
            ...state,
            events,
            rows: [...state.rows, row],
            status: "error",
            endedAt: evt.at,
            error: { message: evt.message, type: evt.type },
          }
        }

        case "start":
          return { ...state, events, following: evt.following === true }

        case "done":
        case "assistant_done":
        default:
          return { ...state, events }
      }
    }
  }
}

export interface UseRunStream {
  state: StreamState
  start: (
    preset: string,
    incidentId: string,
    enabledSkills?: string[],
    enabledServers?: string[],
  ) => void
  /** Watch a run that is executing on the server as if it were started here. */
  follow: (runId: string, preset: string, incidentId: string) => void
  replay: (runId: string, preset: string, incidentId: string) => void
  /** Stop the run on the server; its stream ends with a "Run stopped" error. */
  cancel: () => void
  reset: () => void
}

/**
 * Starts or attaches to a run and reduces every named SSE frame from
 * ``/runs/:id/events`` into structured StreamState. Runs execute on the
 * server: closing this stream (reload, another page) never stops one, and
 * EventSource's automatic reconnect resumes after the last frame received.
 * The frames are the same live and replayed, so the reducer doesn't branch
 * on mode - "live" only means "show it as the current run".
 */
export function useRunStream(): UseRunStream {
  const [state, dispatch] = useReducer(reduce, INITIAL)
  const sourceRef = useRef<EventSource | null>(null)

  const stop = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  const reset = useCallback(() => {
    stop()
    dispatch({ type: "reset" })
  }, [stop])

  const openStream = useCallback(
    (
      url: string,
      mode: StreamMode,
      preset: string,
      incidentId: string,
      runId?: string,
    ) => {
      stop()
      const now = Date.now()
      dispatch({ type: "start", mode, preset, incidentId, runId, at: now })

      const es = new EventSource(url)
      sourceRef.current = es

      const onEvent = (kind: RunEvent["kind"]) => (e: MessageEvent<string>) => {
        try {
          const data = e.data ? JSON.parse(e.data) : {}
          // Server stamps every payload with `at` (wall-clock ms). For live
          // runs this is within ms of Date.now(); for replay it carries the
          // original timing forward so elapsed times stay accurate. Fall
          // back to client time only if the server didn't send one.
          const dataObj = (data && typeof data === "object" ? data : {}) as Record<string, unknown>
          const at = typeof dataObj.at === "number" ? (dataObj.at as number) : Date.now()
          const evt = { kind, ...dataObj, at } as RunEvent
          dispatch({ type: "event", event: evt })
          if (kind === "done") {
            dispatch({ type: "done", at })
            stop()
          }
          if (kind === "agent_error") {
            stop()
          }
        } catch (err) {
          console.error(`[useRunStream] failed to parse ${kind} event:`, err, e.data)
        }
      }

      const eventNames: RunEvent["kind"][] = [
        "start",
        "text",
        "reasoning",
        "tool",
        "tool_result",
        "handoff",
        "assistant_done",
        "done",
        "agent_error",
        "metrics",
        "metrics_delta",
      ]
      for (const name of eventNames) {
        es.addEventListener(name, onEvent(name) as EventListener)
      }

      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) {
          dispatch({
            type: "error",
            message: "Connection closed",
            errorType: "EventSourceError",
            at: Date.now(),
          })
          stop()
        }
      }
    },
    [stop],
  )

  const start = useCallback(
    (
      preset: string,
      incidentId: string,
      enabledSkills?: string[],
      enabledServers?: string[],
    ) => {
      createRun(preset, incidentId, enabledSkills, enabledServers)
        .then((runId) => openStream(runEventsUrl(runId), "live", preset, incidentId, runId))
        .catch((err: unknown) => {
          dispatch({
            type: "error",
            message: err instanceof Error ? err.message : String(err),
            errorType: "StartError",
            at: Date.now(),
          })
        })
    },
    [openStream],
  )

  const follow = useCallback(
    (runId: string, preset: string, incidentId: string) => {
      openStream(runEventsUrl(runId), "live", preset, incidentId, runId)
    },
    [openStream],
  )

  const replay = useCallback(
    (runId: string, preset: string, incidentId: string) => {
      openStream(runEventsUrl(runId), "replay", preset, incidentId, runId)
    },
    [openStream],
  )

  const runId = state.runId
  const cancel = useCallback(() => {
    if (!runId) return
    cancelRun(runId).catch((err: unknown) => {
      console.error("[useRunStream] cancel failed:", err)
    })
  }, [runId])

  useEffect(() => {
    return () => {
      sourceRef.current?.close()
    }
  }, [])

  return { state, start, follow, replay, cancel, reset }
}
