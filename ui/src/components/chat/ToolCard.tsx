import { useState, type ReactNode } from "react"
import { ChevronRight, XCircle } from "lucide-react"
import { CodeBlock } from "@/components/shared/code-block"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Spinner } from "@/components/ui/spinner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { elapsedSeconds } from "@/lib/format"
import type { ToolCall } from "@/lib/types"
import { extractSkillName, toolStyle } from "@/components/tools/tool-styles"
import { ToolResultRouter } from "@/components/tools/ToolResultRouter"
import { sourceStyle } from "@/components/tools/subagent-styles"

interface ToolCardProps {
  call: ToolCall
  /**
   * Controlled-mode open state. When provided, ToolCard does not manage
   * its own open state. Used by EventStream for sub-agent containers
   * where the parent owns the auto-collapse-on-completion rule.
   */
  open?: boolean
  onToggle?: (next: boolean) => void
  /**
   * Optional content rendered inside the expanded body in place of the
   * default Input / Result / Raw tabs. Used to nest a sub-agent's event
   * stream inside the supervisor's call to that sub-agent.
   */
  children?: ReactNode
  /**
   * When true, render sub-agent group chrome: an icon chip tinted with the
   * sub-agent's ``--agent-*`` colour and a muted header strip, so group
   * containers are visually distinct from leaf MCP cards.
   */
  accentBySubAgent?: boolean
  /**
   * When true, render a transient ring around the card. EventStream
   * toggles this for ~1.5s after the user clicks a Timeline row, so
   * the scrolled-to card flashes briefly as visual confirmation.
   */
  highlight?: boolean
}

type BodyTab = "input" | "result" | "raw"

const TAB_TRIGGER_CLS = "text-[11px] tracking-wider uppercase"

function parseInput(input: unknown): unknown {
  if (typeof input !== "string") return input
  try {
    return JSON.parse(input)
  } catch {
    return input
  }
}

export function ToolCard({
  call,
  open: controlledOpen,
  onToggle,
  children,
  accentBySubAgent = false,
  highlight = false,
}: ToolCardProps) {
  const style = toolStyle(call.name, call.input)
  const Icon = style.icon

  // Uncontrolled-mode default: every card starts closed. Sub-agent
  // containers always pass `open` explicitly.
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false)

  // Active body tab; the pretty-printed result is what you open a card for.
  const [tab, setTab] = useState<BodyTab>("result")
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? !!controlledOpen : uncontrolledOpen
  const setOpen = (next: boolean) => {
    if (isControlled) onToggle?.(next)
    else setUncontrolledOpen(next)
  }

  const parsed = parseInput(call.input)
  const inputPretty =
    parsed && typeof parsed === "object"
      ? JSON.stringify(parsed, null, 2)
      : String(parsed ?? "")

  // Pretty-print the raw result string for the "Raw" view: re-indent if it's
  // JSON, otherwise show the string as-is.
  const resultRaw = typeof call.result === "string" ? call.result : ""
  let resultPretty = resultRaw
  try {
    resultPretty = JSON.stringify(JSON.parse(resultRaw), null, 2)
  } catch {
    /* not JSON - leave as the raw string */
  }

  const skillName = call.name === "skills" ? extractSkillName(call.input) : null
  const duration = elapsedSeconds(call.startedAt, call.completedAt)

  // Sub-agent containers identify their group through an accent-tinted icon
  // chip in the header (hue from the sub-agent's source colour) instead of
  // card-edge decoration. ``call.name`` matches the sub-agent's source for
  // these calls (triage_agent → source=triage_agent on its child rows).
  const src = accentBySubAgent ? sourceStyle(call.name) : null
  const AgentIcon = src?.icon

  return (
    <Card
      data-tool-id={call.id}
      className={cn(
        "gap-0 overflow-hidden border-border py-0 transition-shadow duration-200",
        style.destructive && "border-destructive/50",
        highlight && "shadow-lg ring-2 shadow-primary/20 ring-primary/70",
      )}
    >
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger
          className={cn(
            "group/tool-card flex w-full items-center gap-2 px-3 text-left transition-colors",
            accentBySubAgent
              ? "bg-muted/40 py-2.5 hover:bg-muted/60"
              : "py-2 hover:bg-muted/40",
          )}
        >
          <ChevronRight className="size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]/tool-card:rotate-90" />
          {src && AgentIcon ? (
            <span
              className="flex size-6 shrink-0 items-center justify-center rounded-md"
              style={{
                background: `color-mix(in oklab, ${src.accent} 15%, transparent)`,
                color: src.accent,
              }}
            >
              <AgentIcon className="size-3.5" />
            </span>
          ) : (
            <Icon
              className={cn(
                "size-3.5 shrink-0",
                style.tint ?? (style.destructive ? "text-destructive" : "text-muted-foreground"),
              )}
            />
          )}
          <span
            className={cn(
              "min-w-0 truncate text-sm font-medium",
              accentBySubAgent && "font-semibold",
            )}
          >
            {style.label}
          </span>
          {skillName && (
            <span className="min-w-0 shrink truncate font-mono text-xs text-warning">
              → {skillName}
            </span>
          )}
          {/* No input args and no success badge in the header: only an
              in-flight spinner or a failure badge. */}
          <span className="ml-auto flex shrink-0 items-center gap-2">
            {duration && (
              <span className="text-xs tabular-nums text-muted-foreground">
                {duration}
              </span>
            )}
            {call.status === "pending" && (
              <Spinner className="size-3.5 text-muted-foreground" />
            )}
            {call.status === "error" && (
              <Badge variant="destructive" className="gap-1">
                <XCircle className="size-3" />
                error
              </Badge>
            )}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="border-t border-border bg-background/30 px-3 pb-3">
            {children !== undefined ? (
              // Sub-agent container path: render nested events. The
              // sub-agent's final structured output is the last text node
              // in the children, so no separate Result block is needed.
              <div className="space-y-2 pt-3">{children}</div>
            ) : (
              <Tabs
                value={tab}
                onValueChange={(v) => setTab(v as BodyTab)}
                className="pt-3"
              >
                <TabsList className="w-full">
                  <TabsTrigger value="input" className={TAB_TRIGGER_CLS}>
                    Input
                  </TabsTrigger>
                  <TabsTrigger value="result" className={TAB_TRIGGER_CLS}>
                    Result
                  </TabsTrigger>
                  <TabsTrigger value="raw" className={TAB_TRIGGER_CLS}>
                    Raw
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="input">
                  <CodeBlock maxHClassName="max-h-72">
                    {inputPretty || "(empty)"}
                  </CodeBlock>
                </TabsContent>
                <TabsContent value="result">
                  <ResultBody call={call} resultRaw={resultRaw}>
                    <ToolResultRouter call={call} />
                  </ResultBody>
                </TabsContent>
                <TabsContent value="raw">
                  <ResultBody call={call} resultRaw={resultRaw}>
                    <CodeBlock maxHClassName="max-h-96">{resultPretty}</CodeBlock>
                  </ResultBody>
                </TabsContent>
              </Tabs>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}

interface ResultBodyProps {
  call: ToolCall
  resultRaw: string
  children: ReactNode
}

/** Shared Result / Raw tab body: placeholder until the result lands. */
function ResultBody({ call, resultRaw, children }: ResultBodyProps) {
  if (call.result == null) {
    return (
      <div className="flex items-center gap-2 rounded-md bg-muted/40 p-2 text-xs text-muted-foreground italic">
        <Spinner className="size-3" /> Waiting for result…
      </div>
    )
  }
  if (resultRaw.trim().length === 0) {
    return (
      <div className="rounded-md bg-muted/40 p-2 text-xs text-muted-foreground italic">
        No result returned
      </div>
    )
  }
  return <>{children}</>
}
