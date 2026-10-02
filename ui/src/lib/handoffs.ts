import { SUBAGENT_TOOL_NAMES } from "@/lib/eventTree"
import { formatTokens } from "@/lib/format"
import type { RunEvent, Source, ToolCall } from "@/lib/types"

/**
 * What passed between the agents on a run, one entry per agent call.
 *
 * The supervisor briefs a specialist through a tool call and gets its answer
 * back as the tool result; the specialists never see each other's work. Both
 * sides of every handoff are already in the stream (the supervisor's tool
 * input and result). ``handoff`` frames add what the agent itself started
 * from - the exact prompt (for the reporter, the whole case file the server
 * composes, not just the supervisor's verdict), system prompt, tools, model -
 * and are only on runs recorded since they were added.
 *
 * Each model call's prompt size (``metrics_delta.inputTokens``, cached reads
 * included) is the agent's context window at that call, so ``modelCalls``
 * shows it growing.
 */

export const ROOT_CALL_ID = "supervisor"

export interface ModelCall {
  at: number
  /** Tokens sent to the model: the whole context at this call. */
  inputTokens: number
  outputTokens: number
}

export interface AgentContext {
  prompt: string
  systemPrompt: string
  tools: string[]
  model: string | null
  priorMessages: number
}

export interface AgentCall {
  /** The supervisor's tool call that started it, or ROOT_CALL_ID. */
  id: string
  source: Source
  /** What the caller wrote: the supervisor's tool argument, or the run prompt. */
  brief: string
  /** What came back: the tool result, or the supervisor's closing summary. */
  returned?: string
  status: "pending" | "success" | "error"
  startedAt: number
  completedAt?: number
  /** From the ``handoff`` frame; undefined on older runs. */
  context?: AgentContext
  modelCalls: ModelCall[]
}

/** Characters per token, for the "≈ tokens" next to a handoff's length. */
const CHARS_PER_TOKEN = 4

export function approxTokens(text: string): number {
  return Math.round(text.length / CHARS_PER_TOKEN)
}

/** "723 chars · ≈181 tokens" */
export function sizeLabel(text: string): string {
  return `${text.length.toLocaleString("en-US")} chars · ≈${formatTokens(approxTokens(text))} tokens`
}

export function priorLabel(prior: number): string {
  return prior === 0 ? "fresh agent" : `holds ${prior} earlier messages`
}

/**
 * The text of a supervisor → sub-agent tool input. Each sub-agent tool takes
 * one string argument, so the brief is that string. While the call is still
 * streaming the input is a JSON prefix (``{"brief": "Failing identi``); show
 * the value so far.
 */
export function briefText(input: unknown): string {
  let value = input
  if (typeof input === "string") {
    try {
      value = JSON.parse(input)
    } catch {
      return partialStringValue(input)
    }
  }
  if (value && typeof value === "object") {
    const strings = Object.values(value).filter((v): v is string => typeof v === "string")
    return strings.length === 1 ? strings[0] : JSON.stringify(value, null, 2)
  }
  return value == null ? "" : String(value)
}

function partialStringValue(raw: string): string {
  const m = raw.match(/^\s*\{\s*"[^"]*"\s*:\s*"((?:[^"\\]|\\.)*)/s)
  if (!m) return raw
  try {
    return JSON.parse(`"${m[1]}"`) as string
  } catch {
    return m[1].replace(/\\n/g, "\n").replace(/\\"/g, '"')
  }
}

/**
 * One AgentCall per supervisor → sub-agent call, plus the supervisor's own
 * (ROOT_CALL_ID) first, then in start order. Single pass over the events.
 *
 * A sub-agent runs one call at a time, so its frames belong to the call last
 * opened for its source - the same rule the event tree nests by.
 */
export function buildAgentCalls(
  events: RunEvent[],
  toolCalls: Map<string, ToolCall>,
  runEnded: boolean,
): AgentCall[] {
  const calls = new Map<string, AgentCall>()
  const openBySource = new Map<Source, AgentCall>()
  // The supervisor's text since its last tool call: its closing summary
  // once the run ends.
  let supervisorText = ""

  for (const evt of events) {
    switch (evt.kind) {
      case "start": {
        const root: AgentCall = {
          id: ROOT_CALL_ID,
          source: "supervisor",
          brief: "",
          status: "pending",
          startedAt: evt.at,
          modelCalls: [],
        }
        calls.set(ROOT_CALL_ID, root)
        openBySource.set("supervisor", root)
        break
      }
      case "handoff": {
        const call = evt.callId ? calls.get(evt.callId) : calls.get(ROOT_CALL_ID)
        if (!call) break
        call.context = {
          prompt: evt.prompt,
          systemPrompt: evt.systemPrompt,
          tools: evt.tools,
          model: evt.model,
          priorMessages: evt.priorMessages,
        }
        if (call.id === ROOT_CALL_ID) call.brief = evt.prompt
        openBySource.set(evt.source, call)
        break
      }
      case "tool": {
        if (evt.source !== "supervisor") break
        supervisorText = ""
        if (!SUBAGENT_TOOL_NAMES.has(evt.name) || calls.has(evt.id)) break
        const call: AgentCall = {
          id: evt.id,
          source: evt.name,
          brief: "",
          status: "pending",
          startedAt: evt.at,
          modelCalls: [],
        }
        calls.set(evt.id, call)
        openBySource.set(evt.name, call)
        break
      }
      case "metrics_delta": {
        openBySource.get(evt.source)?.modelCalls.push({
          at: evt.at,
          inputTokens: evt.inputTokens,
          outputTokens: evt.outputTokens,
        })
        break
      }
      case "text": {
        if (evt.source === "supervisor") supervisorText += evt.delta
        break
      }
      case "agent_error": {
        const root = calls.get(ROOT_CALL_ID)
        if (root) {
          root.status = "error"
          root.completedAt ??= evt.at
        }
        break
      }
      case "metrics":
      case "done": {
        const root = calls.get(ROOT_CALL_ID)
        if (root && (evt.kind === "done" || evt.source === "supervisor")) {
          root.status = "success"
          root.completedAt ??= evt.at
        }
        break
      }
    }
  }

  // Brief, answer and status from the supervisor's tool calls (the reducer
  // has already merged their streamed input and their results).
  for (const call of calls.values()) {
    if (call.id === ROOT_CALL_ID) continue
    const tool = toolCalls.get(call.id)
    if (!tool) continue
    call.brief = briefText(tool.input)
    call.returned = tool.result
    call.status = tool.status
    call.completedAt = tool.completedAt
  }
  const root = calls.get(ROOT_CALL_ID)
  if (root && runEnded && supervisorText.trim()) root.returned = supervisorText.trim()

  return [...calls.values()].sort((a, b) =>
    a.id === ROOT_CALL_ID ? -1 : b.id === ROOT_CALL_ID ? 1 : a.startedAt - b.startedAt,
  )
}

/**
 * Sub-agent calls grouped into the steps of the investigation: calls that
 * overlap in time (diagnosis and forensics, fanned out in one turn) share a
 * step.
 */
export function handoffSteps(calls: AgentCall[], now: number): AgentCall[][] {
  const steps: AgentCall[][] = []
  let stepEnd = -Infinity
  for (const call of calls) {
    if (call.id === ROOT_CALL_ID) continue
    const end = call.completedAt ?? now
    if (steps.length > 0 && call.startedAt < stepEnd) {
      steps[steps.length - 1].push(call)
      stepEnd = Math.max(stepEnd, end)
    } else {
      steps.push([call])
      stepEnd = end
    }
  }
  return steps
}

/** The call's context window: first and largest model-call prompt. */
export function contextRange(call: AgentCall): { first: number; peak: number } | null {
  if (call.modelCalls.length === 0) return null
  return {
    first: call.modelCalls[0].inputTokens,
    peak: Math.max(...call.modelCalls.map((m) => m.inputTokens)),
  }
}
