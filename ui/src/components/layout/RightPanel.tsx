import { CheckCircle2, PanelRightClose, XCircle } from "lucide-react"
import { EmptyState } from "@/components/shared/empty-state"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { SUBAGENT_TOOL_NAMES } from "@/lib/eventTree"
import { elapsedSeconds } from "@/lib/format"
import { ROOT_CALL_ID, type AgentCall } from "@/lib/handoffs"
import type { ToolCall } from "@/lib/types"
import { sourceStyle } from "@/components/tools/subagent-styles"
import { extractSkillName, toolStyle } from "@/components/tools/tool-styles"
import { ContextChart } from "@/components/handoffs/ContextChart"

interface RightPanelProps {
  onClose: () => void
  toolCalls: Map<string, ToolCall>
  /** Per agent call, for the context-window chart; and the run's span. */
  agentCalls: AgentCall[]
  runStart: number
  runEnd: number
  /** Fires when the user clicks a Timeline row - the EventStream in the
   *  chat pane should scroll to and expand the matching ToolCard. */
  onSelectTool: (toolCallId: string) => void
}

export function RightPanel({
  onClose,
  toolCalls,
  agentCalls,
  runStart,
  runEnd,
  onSelectTool,
}: RightPanelProps) {
  const callList = Array.from(toolCalls.values()).sort((a, b) => a.startedAt - b.startedAt)

  return (
    <aside className="flex h-full min-w-0 flex-col border-l border-border bg-sidebar text-sidebar-foreground">
      <div className="flex shrink-0 items-center gap-2 px-4 pt-4">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon-sm"
              variant="ghost"
              onClick={onClose}
              className="shrink-0 text-muted-foreground hover:text-foreground"
              aria-label="Collapse panel"
            >
              <PanelRightClose className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="flex items-center gap-2">
            Collapse
            <Kbd>]</Kbd>
          </TooltipContent>
        </Tooltip>
        <span className="text-sm font-medium">Timeline</span>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="px-4 py-4">
          {agentCalls.some((c) => c.modelCalls.length > 0) && (
            <div className="mb-3 space-y-2">
              <div className="text-xs tracking-wider text-muted-foreground uppercase">
                Context window
              </div>
              <ContextChart
                calls={agentCalls}
                start={runStart}
                end={runEnd}
                height={160}
                compact
                onSelect={(id) => id !== ROOT_CALL_ID && onSelectTool(id)}
              />
            </div>
          )}
          {callList.length === 0 ? (
            <EmptyState title="No tool calls yet." />
          ) : (
            <TimelineTree calls={callList} onSelectTool={onSelectTool} />
          )}
        </div>
      </ScrollArea>
    </aside>
  )
}

interface TreeNode {
  call: ToolCall
  children: ToolCall[]
}

/**
 * Build a 2-level tree out of the flat tool-call list:
 *
 *   supervisor:triage_agent            ← root
 *     triage_agent:get_incident        ← child
 *   supervisor:kafka_diagnosis_agent   ← root
 *     kafka_diagnosis_agent:skills     ← child
 *     kafka_diagnosis_agent:get_topic  ← child
 *     …
 *
 * The supervisor's call to a sub-agent stays open as the "current parent
 * for source=<name>" until either (a) the supervisor calls the same
 * sub-agent again (replacing the parent), or (b) the run ends. Calls with
 * an unknown parent - e.g. an unexpected supervisor tool, or a sub-agent
 * call that arrived before its parent's spawn event somehow - degrade
 * gracefully to a root node.
 */
function buildTimelineTree(calls: ToolCall[]): TreeNode[] {
  const roots: TreeNode[] = []
  const openParents = new Map<string, TreeNode>() // source-name → node

  for (const call of calls) {
    if (call.source === "supervisor") {
      const node: TreeNode = { call, children: [] }
      roots.push(node)
      if (SUBAGENT_TOOL_NAMES.has(call.name)) {
        openParents.set(call.name, node)
      }
      continue
    }
    const parent = openParents.get(call.source)
    if (parent) {
      parent.children.push(call)
    } else {
      // Orphan - render as root so it isn't silently dropped.
      roots.push({ call, children: [] })
    }
  }
  return roots
}

interface TimelineTreeProps {
  calls: ToolCall[]
  onSelectTool: (toolCallId: string) => void
}

function TimelineTree({ calls, onSelectTool }: TimelineTreeProps) {
  const tree = buildTimelineTree(calls)
  return (
    <ul className="space-y-2">
      {tree.map((node) => (
        <li key={node.call.id} className="space-y-0.5">
          <TimelineRow call={node.call} depth={0} onSelect={onSelectTool} />
          {node.children.length > 0 && (
            <ul className="mt-0.5 ml-2 space-y-0.5 border-l border-border/60 pl-3">

              {node.children.map((child) => (
                <li key={child.id}>
                  <TimelineRow call={child} depth={1} onSelect={onSelectTool} />
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  )
}

interface TimelineRowProps {
  call: ToolCall
  depth: number
  onSelect: (toolCallId: string) => void
}

function TimelineRow({ call, depth, onSelect }: TimelineRowProps) {
  const tool = toolStyle(call.name, call.input)
  const ToolIcon = tool.icon
  const skillName = call.name === "skills" ? extractSkillName(call.input) : null

  // Sub-agent group rows mirror the stream's ToolCard identity: an
  // accent-tinted icon chip + muted strip. Leaf rows get the plain tool
  // icon - muted, or brand-tinted for third-party marks.
  const isGroup = depth === 0 && SUBAGENT_TOOL_NAMES.has(call.name)
  const src = isGroup ? sourceStyle(call.name) : null
  const AgentIcon = src?.icon

  return (
    <button
      type="button"
      onClick={() => onSelect(call.id)}
      title="Jump to this step in the live feed"
      className={cn(
        "group flex w-full cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-left text-xs transition-colors hover:border-ring/40 focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none",
        // Roots get the full border; children sit inside a parent rail
        // already, so they go borderless to reduce visual noise.
        depth === 0 ? "border-border/50" : "border-transparent",
        isGroup
          ? "bg-muted/40 hover:bg-muted/60"
          : "bg-card/40 hover:bg-card",
        tool.destructive && "border-destructive/40",
      )}
    >
      {src && AgentIcon ? (
        <span
          className="flex size-5 shrink-0 items-center justify-center rounded-md"
          style={{
            background: `color-mix(in oklab, ${src.accent} 15%, transparent)`,
            color: src.accent,
          }}
        >
          <AgentIcon className="size-3" />
        </span>
      ) : (
        <ToolIcon
          className={cn(
            "size-3.5 shrink-0",
            tool.tint ?? (tool.destructive ? "text-destructive" : "text-muted-foreground"),
          )}
        />
      )}
      <span className="min-w-0 flex-1 truncate">
        <span
          className={cn("text-foreground", isGroup && "font-semibold")}
        >
          {tool.label}
        </span>
        {skillName && (
          <span className="ml-1.5 font-mono text-warning">→ {skillName}</span>
        )}
      </span>
      {depth === 0 && !isGroup && (
        <span className="shrink-0 font-mono text-muted-foreground">
          {sourceStyle(call.source).short}
        </span>
      )}
      {call.status === "pending" ? (
        <Spinner className="size-3 shrink-0 text-muted-foreground" />
      ) : call.status === "error" ? (
        <XCircle className="size-3 shrink-0 text-destructive" />
      ) : (
        <CheckCircle2 className="size-3 shrink-0 text-success" />
      )}
      <span className="w-9 shrink-0 text-right tabular-nums text-muted-foreground">
        {elapsedSeconds(call.startedAt, call.completedAt) ?? "…"}
      </span>
    </button>
  )
}
