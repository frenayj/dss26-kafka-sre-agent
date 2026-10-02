import type { Row, ToolCall } from "@/lib/types"

/** Sub-agent closure names - supervisor's ``@tool`` wrappers. Tool calls
 *  with these names become container nodes that nest their sub-agent's
 *  events (and, in the Timeline, their tool calls) as children. */
export const SUBAGENT_TOOL_NAMES = new Set([
  "triage_agent",
  "kafka_diagnosis_agent",
  "code_forensics_agent",
  "reporter_agent",
])

export type TextNode = { kind: "text"; row: Extract<Row, { kind: "text" }> }
export type ReasoningNode = {
  kind: "reasoning"
  row: Extract<Row, { kind: "reasoning" }>
}
export type ErrorNode = { kind: "error"; row: Extract<Row, { kind: "error" }> }
export type ToolNode = {
  kind: "tool"
  call: ToolCall
  /** True iff this is a supervisor → sub-agent call (container). */
  isSubAgent: boolean
  /** Sub-agent events that ran during this call. Empty for MCP tool calls. */
  children: EventNode[]
}
export type EventNode =
  | TextNode
  | ReasoningNode
  | ErrorNode
  | ToolNode

/**
 * Group the flat ``rows`` list into a hierarchical tree that mirrors the
 * call structure: supervisor events at the root; each supervisor call to
 * a sub-agent becomes a container whose ``children`` are that sub-agent's
 * own events (their text, reasoning, MCP tool calls).
 *
 * Walks chronologically. ``openParents`` maps a sub-agent source name to
 * the currently-open container node for it. A sub-agent's events nest in
 * that container until the supervisor's next call to the same sub-agent
 * opens a new one. Rows whose source has no open container fall back to
 * the root so nothing is silently dropped (orphans).
 *
 * Single pass, O(N).
 */
export function buildEventTree(
  rows: Row[],
  toolCalls: Map<string, ToolCall>,
): EventNode[] {
  const root: EventNode[] = []
  const openParents = new Map<string, ToolNode>()

  for (const row of rows) {
    // Error rows are out-of-band; render them at the supervisor level
    // rather than nesting inside whatever container happens to be open.
    const source = row.kind === "error" ? "supervisor" : row.source
    const parent = source === "supervisor" ? null : openParents.get(source) ?? null
    const bucket = parent ? parent.children : root

    if (row.kind === "tool") {
      const call = toolCalls.get(row.toolCallId)
      // Defensive: a tool row without its corresponding call (race with
      // streaming events) renders as a no-op text placeholder rather than
      // disappearing.
      if (!call) continue
      const isSubAgent = SUBAGENT_TOOL_NAMES.has(call.name)
      const node: ToolNode = {
        kind: "tool",
        call,
        isSubAgent,
        children: [],
      }
      bucket.push(node)
      // Only sub-agent calls open a container; MCP calls stay leaves.
      // Note that we use the tool *name* (the sub-agent's closure name)
      // as the key, which matches the ``source`` on rows the sub-agent
      // will subsequently emit.
      if (isSubAgent) {
        openParents.set(call.name, node)
      }
    } else if (row.kind === "text") {
      // Merge into the bucket's open text node when there is one. The
      // reducer only coalesces deltas that are ADJACENT in the flat stream,
      // but parallel sub-agents (diagnosis + forensics) interleave their
      // deltas, so a single agent's burst arrives as several non-adjacent
      // rows. Bucketing by source de-interleaves them, so consecutive text
      // nodes here belong to one burst and render as one paragraph. A tool
      // call or reasoning switch pushes a non-text node between bursts, which
      // ends the merge naturally.
      const last = bucket[bucket.length - 1]
      if (last && last.kind === "text" && last.row.source === row.source) {
        last.row = { ...last.row, content: last.row.content + row.content }
      } else {
        bucket.push({ kind: "text", row })
      }
    } else if (row.kind === "reasoning") {
      const last = bucket[bucket.length - 1]
      if (last && last.kind === "reasoning" && last.row.source === row.source) {
        last.row = { ...last.row, content: last.row.content + row.content }
      } else {
        bucket.push({ kind: "reasoning", row })
      }
    } else if (row.kind === "error") {
      bucket.push({ kind: "error", row })
    }
  }

  return root
}

/**
 * Build a child-toolId → parent-toolId map by walking the event tree.
 * Returns ``null`` for tools that sit at the root (supervisor calls).
 * Used by EventStream to open the entire ancestor chain when the user
 * focuses a deeply-nested tool via the Timeline.
 */
export function buildParentMap(tree: EventNode[]): Map<string, string | null> {
  const map = new Map<string, string | null>()
  function walk(nodes: EventNode[], parent: string | null) {
    for (const node of nodes) {
      if (node.kind !== "tool") continue
      map.set(node.call.id, parent)
      if (node.children.length > 0) walk(node.children, node.call.id)
    }
  }
  walk(tree, null)
  return map
}
