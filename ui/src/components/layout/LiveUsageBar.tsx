import { useMemo } from "react"
import { BookOpen, Clock, Coins, Database, Wrench } from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Separator } from "@/components/ui/separator"
import { StatusBadge } from "@/components/shared/status-badge"
import { cn } from "@/lib/utils"
import { formatTokens, formatMs } from "@/lib/format"
import type { AgentMetrics, ToolCall } from "@/lib/types"
import { extractSkillName } from "@/components/tools/tool-styles"

interface LiveUsageBarProps {
  agentMetrics: Map<string, AgentMetrics>
  toolCalls: Map<string, ToolCall>
}

interface Totals {
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
  latencyMs: number
}

function aggregate(metrics: Map<string, AgentMetrics>): Totals {
  let inputTokens = 0
  let outputTokens = 0
  let totalTokens = 0
  let cacheReadTokens = 0
  let cacheWriteTokens = 0
  let latencyMs = 0
  for (const m of metrics.values()) {
    inputTokens += m.inputTokens
    outputTokens += m.outputTokens
    totalTokens += m.totalTokens
    cacheReadTokens += m.cacheReadTokens ?? 0
    cacheWriteTokens += m.cacheWriteTokens ?? 0
    latencyMs += m.latencyMs
  }
  return { inputTokens, outputTokens, totalTokens, cacheReadTokens, cacheWriteTokens, latencyMs }
}

/** Extract distinct skill names from every `skills` tool call seen so far. */
function skillsActivated(toolCalls: Map<string, ToolCall>): string[] {
  const seen = new Set<string>()
  for (const call of toolCalls.values()) {
    if (call.name !== "skills") continue
    const name = extractSkillName(call.input)
    if (name) seen.add(name)
  }
  return Array.from(seen)
}

const SUBAGENT_TOOLS = new Set([
  "triage_agent",
  "kafka_diagnosis_agent",
  "code_forensics_agent",
  "reporter_agent",
])

interface ToolBreakdown {
  total: number
  subagent: number
  skill: number
  mcp: number
}

/** Categorize tool calls so the chip's tooltip can break down composition. */
function categorize(toolCalls: Map<string, ToolCall>): ToolBreakdown {
  let subagent = 0
  let skill = 0
  let mcp = 0
  for (const call of toolCalls.values()) {
    if (SUBAGENT_TOOLS.has(call.name)) subagent++
    else if (call.name === "skills") skill++
    else mcp++
  }
  return { total: toolCalls.size, subagent, skill, mcp }
}

/**
 * Sticky single-line stats strip showing live cumulative token usage, skill
 * activations, and total latency for the current run. Hidden when the run
 * is idle and no metrics have arrived yet.
 *
 * The token totals are summed across every `metrics`/`metrics_delta` event
 * the reducer has seen - the same numbers the agent exports to its
 * OpenTelemetry traces (Phoenix).
 * Cache hit rate is computed against total input tokens, surfacing the
 * impact of prompt caching at a glance.
 */
export function LiveUsageBar({ agentMetrics, toolCalls }: LiveUsageBarProps) {
  const totals = useMemo(() => aggregate(agentMetrics), [agentMetrics])
  const skills = useMemo(() => skillsActivated(toolCalls), [toolCalls])
  const tools = useMemo(() => categorize(toolCalls), [toolCalls])

  // Hide until we have anything to show - keeps the chat area clean before
  // the first run starts.
  const hasData =
    totals.totalTokens > 0 ||
    skills.length > 0 ||
    totals.latencyMs > 0 ||
    tools.total > 0
  if (!hasData) return null

  const cacheHitPct =
    totals.cacheReadTokens > 0 && totals.inputTokens > 0
      ? Math.round((totals.cacheReadTokens / totals.inputTokens) * 100)
      : 0

  return (
    <div className="px-6 py-2 border-b border-border/60 bg-card/30 flex items-center gap-4 text-xs shrink-0">
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5 cursor-help">
            <Coins className="size-3.5 text-muted-foreground" />
            <span className="font-mono text-foreground">
              {formatTokens(totals.inputTokens)}
            </span>
            <span className="text-muted-foreground">in</span>
            <span className="text-muted-foreground">·</span>
            <span className="font-mono text-foreground">
              {formatTokens(totals.outputTokens)}
            </span>
            <span className="text-muted-foreground">out</span>
            {cacheHitPct > 0 && (
              <StatusBadge
                tone={cacheHitPct >= 50 ? "success" : "warning"}
                className="ml-1 font-mono"
              >
                cache {cacheHitPct}%
              </StatusBadge>
            )}
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs space-y-0.5">
          <div className="font-medium">Cumulative token usage</div>
          <div className="font-mono">
            input {formatTokens(totals.inputTokens)} · output{" "}
            {formatTokens(totals.outputTokens)} · total{" "}
            {formatTokens(totals.totalTokens)}
          </div>
          {totals.cacheReadTokens > 0 && (
            <div className="font-mono text-success">
              cache hits {formatTokens(totals.cacheReadTokens)} ({cacheHitPct}% of input)
            </div>
          )}
          {totals.cacheWriteTokens > 0 && (
            <div className="font-mono text-muted-foreground">
              cache writes {formatTokens(totals.cacheWriteTokens)}
            </div>
          )}
        </TooltipContent>
      </Tooltip>

      <Separator orientation="vertical" className="h-3 self-center" />

      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5 cursor-help">
            <BookOpen
              className={cn(
                "size-3.5",
                skills.length > 0 ? "text-warning" : "text-muted-foreground",
              )}
            />
            <span className="font-mono text-foreground">{skills.length}</span>
            <span className="text-muted-foreground">
              skill{skills.length === 1 ? "" : "s"}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          {skills.length === 0 ? (
            <div className="text-muted-foreground">No skills activated yet.</div>
          ) : (
            <>
              <div className="font-medium mb-1">Activated skills</div>
              <ul className="space-y-0.5">
                {skills.map((name) => (
                  <li key={name} className="font-mono text-warning">
                    📘 {name}
                  </li>
                ))}
              </ul>
            </>
          )}
        </TooltipContent>
      </Tooltip>

      <Separator orientation="vertical" className="h-3 self-center" />

      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5 cursor-help">
            <Wrench className="size-3.5 text-muted-foreground" />
            <span className="font-mono text-foreground">{tools.total}</span>
            <span className="text-muted-foreground">
              tool{tools.total === 1 ? "" : "s"}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          {tools.total === 0 ? (
            <div className="text-muted-foreground">No tools called yet.</div>
          ) : (
            <>
              <div className="font-medium mb-1">Tool calls so far</div>
              <ul className="space-y-0.5 font-mono">
                {tools.subagent > 0 && (
                  <li>sub-agents · {tools.subagent}</li>
                )}
                {tools.skill > 0 && (
                  <li className="text-warning">skills · {tools.skill}</li>
                )}
                {tools.mcp > 0 && <li>MCP · {tools.mcp}</li>}
              </ul>
            </>
          )}
        </TooltipContent>
      </Tooltip>

      <Separator orientation="vertical" className="h-3 self-center" />

      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5 cursor-help">
            <Clock className="size-3.5 text-muted-foreground" />
            <span className="font-mono text-foreground">{formatMs(totals.latencyMs)}</span>
            <span className="text-muted-foreground">model</span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          Cumulative model latency across all agents. Updated once each
          sub-agent completes.
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <div className="ml-auto flex items-center gap-1.5 cursor-help text-muted-foreground">
            <Database className="size-3.5" />
            <span className="font-mono">{agentMetrics.size}</span>
            <span>agent{agentMetrics.size === 1 ? "" : "s"}</span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          Number of agents that have reported metrics so far. See the
          Timeline tab for per-agent breakdown.
        </TooltipContent>
      </Tooltip>
    </div>
  )
}
