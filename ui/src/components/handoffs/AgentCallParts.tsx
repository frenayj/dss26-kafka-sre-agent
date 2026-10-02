import type { ReactNode } from "react"
import { ChevronRight, CornerDownRight, CornerUpLeft, Layers } from "lucide-react"
import { CodeBlock } from "@/components/shared/code-block"
import { Expander } from "@/components/shared/expander"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { formatTokens } from "@/lib/format"
import {
  approxTokens,
  contextRange,
  priorLabel,
  sizeLabel,
  type AgentCall,
} from "@/lib/handoffs"
import { parseTriage } from "@/lib/triage"
import { cn } from "@/lib/utils"
import { Markdown } from "@/components/tools/Markdown"
import { sourceStyle } from "@/components/tools/subagent-styles"
import { TriageCard } from "@/components/tools/TriageSummary"
import { ContextBars } from "./ContextChart"

/**
 * An answer a sub-agent handed back. Triage answers with a JSON object; when
 * it parses, it shows as a card, with the exact text one click away. Anything
 * else shows as the Markdown it is.
 */
export function ReturnedBody({ source, text }: { source: string; text: string }) {
  const triage = source === "triage_agent" ? parseTriage(text) : null
  if (!triage) return <Markdown content={text || "_(empty)_"} className="text-sm [&_p]:my-1.5" />
  return (
    <div className="space-y-3 py-1">
      <TriageCard triage={triage} />
      <Expander label="Raw">
        <CodeBlock maxHClassName="max-h-72">{text}</CodeBlock>
      </Expander>
    </div>
  )
}

/**
 * One side of a handoff: the brief an agent was given, or the answer it
 * handed back. Folded to its header line until clicked; the arrow icon takes
 * the sender's colour.
 */
export function HandoffBlock({
  direction,
  label,
  text,
  sender,
  note,
}: {
  direction: "in" | "out"
  label: string
  text: string
  /** Source whose colour marks the block: who wrote it. */
  sender: string
  note?: ReactNode
}) {
  const Icon = direction === "in" ? CornerDownRight : CornerUpLeft
  return (
    <Collapsible className="rounded-md border border-border/70 bg-muted/20">
      <CollapsibleTrigger className="group/handoff flex w-full items-center gap-1.5 px-3 py-2 text-left text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
        <ChevronRight className="size-3.5 shrink-0 transition-transform group-data-[state=open]/handoff:rotate-90" />
        <Icon className="size-3.5 shrink-0" style={{ color: sourceStyle(sender).accent }} />
        {label}
        <span className="ml-auto font-normal tracking-normal normal-case tabular-nums">
          {sizeLabel(text)}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t border-border/70 px-3 py-2">
          {note && <p className="mb-1 text-xs text-muted-foreground">{note}</p>}
          {direction === "out" ? (
            <ReturnedBody source={sender} text={text} />
          ) : (
            <Markdown content={text || "_(empty)_"} className="text-sm [&_p]:my-1.5" />
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function Chip({ children, mono = false }: { children: ReactNode; mono?: boolean }) {
  return (
    <span
      className={cn(
        "rounded border border-border/70 bg-background px-1.5 py-0.5 text-[11px] leading-none text-foreground/80",
        mono && "font-mono",
      )}
    >
      {children}
    </span>
  )
}

/**
 * What else an agent starts the call with, beyond the brief: model, tools,
 * system prompt, earlier turns - and its context window per model call.
 * Collapsed to one line; opens to the full system prompt and tool list.
 */
export function AgentContextRow({ call }: { call: AgentCall }) {
  const ctx = call.context
  const range = contextRange(call)
  const accent = sourceStyle(call.source).accent
  return (
    <Collapsible className="rounded-md border border-border/70 bg-muted/20">
      <CollapsibleTrigger className="group/ctx flex w-full flex-wrap items-center gap-1.5 px-3 py-2 text-left">
        <ChevronRight className="size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]/ctx:rotate-90" />
        <Layers className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="mr-1 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
          Context
        </span>
        {ctx && (
          <>
            {ctx.model && <Chip mono>{ctx.model}</Chip>}
            <Chip>{ctx.tools.length} tools</Chip>
            <Chip>system prompt ≈{formatTokens(approxTokens(ctx.systemPrompt))} tokens</Chip>
            <Chip>{priorLabel(ctx.priorMessages)}</Chip>
          </>
        )}
        {range && (
          <span className="ml-auto flex items-center gap-2 pl-2 text-xs text-muted-foreground tabular-nums">
            <ContextBars modelCalls={call.modelCalls} accent={accent} />
            <span>
              <span className="text-foreground">{formatTokens(range.first)}</span>
              {range.peak !== range.first && (
                <>
                  {" → "}
                  <span className="text-foreground">{formatTokens(range.peak)}</span>
                </>
              )}{" "}
              tokens
            </span>
          </span>
        )}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <AgentContextDetail call={call} className="border-t border-border/70 px-3 py-3" />
      </CollapsibleContent>
    </Collapsible>
  )
}

/** The context in full: per-call sizes, tools, system prompt. */
export function AgentContextDetail({
  call,
  className,
  systemPromptMaxH = "max-h-72",
}: {
  call: AgentCall
  className?: string
  systemPromptMaxH?: string
}) {
  const ctx = call.context
  const accent = sourceStyle(call.source).accent
  return (
    <div className={cn("space-y-3 text-xs", className)}>
      {call.modelCalls.length > 0 && (
        <section className="space-y-1.5">
          <h4 className="font-medium text-muted-foreground">
            Context window per model call
          </h4>
          <div className="flex items-end gap-3">
            <ContextBars
              modelCalls={call.modelCalls}
              accent={accent}
              height={44}
              barWidth={10}
            />
            <span className="pb-0.5 text-muted-foreground tabular-nums">
              {call.modelCalls.map((m) => formatTokens(m.inputTokens)).join(" → ")} tokens
            </span>
          </div>
        </section>
      )}
      {ctx ? (
        <>
          <section className="space-y-1.5">
            <h4 className="font-medium text-muted-foreground">
              Tools ({ctx.tools.length})
            </h4>
            {ctx.tools.length === 0 ? (
              <div className="text-muted-foreground italic">None</div>
            ) : (
              <div className="flex flex-wrap gap-1">
                {ctx.tools.map((t) => (
                  <Chip key={t} mono>
                    {t}
                  </Chip>
                ))}
              </div>
            )}
          </section>
          <section className="space-y-1.5">
            <h4 className="font-medium text-muted-foreground">
              System prompt · {sizeLabel(ctx.systemPrompt)}
            </h4>
            <CodeBlock maxHClassName={systemPromptMaxH}>{ctx.systemPrompt}</CodeBlock>
          </section>
        </>
      ) : (
        <p className="text-muted-foreground italic">
          This run was recorded before agents' context was captured: only the context sizes
          are available. New runs record the system prompt, tools and model too.
        </p>
      )}
    </div>
  )
}
