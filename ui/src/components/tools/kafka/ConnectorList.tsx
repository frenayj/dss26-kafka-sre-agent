import { CodeBlock } from "@/components/shared/code-block"
import { EmptyState } from "@/components/shared/empty-state"
import { SectionHeader } from "@/components/shared/section-header"
import { StatusBadge } from "@/components/shared/status-badge"
import { StatusDot } from "@/components/shared/status-dot"
import { parseToolResult, stateToTone } from "./parse"
import type { ConnectorListData, ConnectorTask } from "./types"
import { JsonView } from "../JsonView"

interface Props {
  result: string
}

/** First few meaningful lines of a task stack trace, for the FAILED excerpt. */
function traceExcerpt(trace: string, maxLines = 4, maxChars = 360): string {
  const lines = trace
    .split("\n")
    .map((l) => l.trimEnd())
    .filter((l) => l.length > 0)
  const excerpt = lines.slice(0, maxLines).join("\n")
  return excerpt.length > maxChars ? excerpt.slice(0, maxChars - 1) + "…" : excerpt
}

/** Strip the package prefix so the class fits the card. */
function shortClassName(className?: string): string | null {
  if (!className) return null
  const parts = className.split(".")
  return parts[parts.length - 1] || className
}

export function ConnectorList({ result }: Props) {
  const parsed = parseToolResult<ConnectorListData>(result, ["data"])
  // Unexpected shape (MCP version skew) - degrade to the JSON view rather
  // than rendering nothing mid-demo.
  if (!parsed.ok || !Array.isArray(parsed.data.data)) {
    return <JsonView content={result} />
  }
  const connectors = parsed.data.data

  if (connectors.length === 0) {
    return (
      <div className="space-y-2">
        <SectionHeader title="Connectors" count={0} />
        <EmptyState title="No connectors found." />
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
      <SectionHeader title="Connectors" count={connectors.length} />

      <div className="space-y-2">
        {connectors.map((connector) => {
          const tasks = connector.tasks ?? []
          const failedTasks = tasks.filter(
            (t) => t.state.toUpperCase() === "FAILED",
          )
          // The connector object can report RUNNING while every task is
          // dead - surface the worst state so the card doesn't lie.
          const effectiveState =
            failedTasks.length > 0 ? "FAILED" : connector.state

          return (
            <div
              key={connector.lrn ?? connector.name}
              className="overflow-hidden rounded-md border border-border bg-card"
            >
              <div className="flex items-center gap-2 px-3 py-2">
                <StatusDot tone={stateToTone(effectiveState)} size="sm" />
                <span className="min-w-0 flex-1 truncate font-mono text-xs font-medium">
                  {connector.name}
                </span>
                {connector.type && (
                  <StatusBadge tone="muted" className="shrink-0">
                    {connector.type}
                  </StatusBadge>
                )}
                <StatusBadge
                  tone={stateToTone(connector.state)}
                  className="shrink-0"
                >
                  {connector.state}
                </StatusBadge>
              </div>

              {(connector.className || connector.cluster) && (
                <div className="flex items-center gap-2 px-3 pb-1.5 font-mono text-[11px] text-muted-foreground">
                  {shortClassName(connector.className) && (
                    <span className="truncate" title={connector.className}>
                      {shortClassName(connector.className)}
                    </span>
                  )}
                  {connector.cluster && (
                    <span className="shrink-0">@ {connector.cluster}</span>
                  )}
                </div>
              )}

              {tasks.length > 0 && (
                <div className="flex flex-wrap gap-1 px-3 pb-2">
                  {tasks.map((task) => (
                    <TaskChip key={task.id} task={task} />
                  ))}
                </div>
              )}

              {failedTasks.map(
                (task) =>
                  task.trace && (
                    <CodeBlock
                      key={`trace-${task.id}`}
                      className="mx-3 mb-2 border-destructive/40 bg-destructive/10 text-[11px] leading-snug text-destructive"
                    >
                      {traceExcerpt(task.trace)}
                    </CodeBlock>
                  ),
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function TaskChip({ task }: { task: ConnectorTask }) {
  return (
    <StatusBadge
      tone={stateToTone(task.state)}
      className="rounded-full font-mono font-normal tracking-normal normal-case"
    >
      task {task.id} · {task.state}
    </StatusBadge>
  )
}
