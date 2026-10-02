import { useState, type ReactNode } from "react"
import { ArrowRight, CornerDownRight, CornerUpLeft, FileText, Siren } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Spinner } from "@/components/ui/spinner"
import { formatTokens } from "@/lib/format"
import {
  ROOT_CALL_ID,
  approxTokens,
  contextRange,
  handoffSteps,
  priorLabel,
  sizeLabel,
  type AgentCall,
} from "@/lib/handoffs"
import { cn } from "@/lib/utils"
import { Markdown } from "@/components/tools/Markdown"
import { sourceStyle } from "@/components/tools/subagent-styles"
import { parseTriage } from "@/lib/triage"
import { AgentContextDetail, ReturnedBody } from "./AgentCallParts"
import { ContextBars, ContextChart } from "./ContextChart"

interface HandoffsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  calls: AgentCall[]
  /** Run time span, for the chart's axis. */
  start: number
  end: number
  incidentId: string | null
}

/** What the detail pane shows: one side of a handoff, or an agent. */
type Selection = { kind: "brief" | "return" | "agent"; callId: string }

/**
 * The run as a chain of handoffs: the incident to the supervisor, the
 * supervisor to each specialist and back (diagnosis and forensics side by
 * side, since they run together), and the supervisor's closing summary.
 *
 * - Top: every agent's context window per model call, on one time axis.
 * - Left: the chain. Each row is brief → agent → answer; click any of them.
 * - Right: the selected handoff in full, or the agent's context (model,
 *   tools, system prompt, earlier turns).
 */
export function HandoffsDialog({
  open,
  onOpenChange,
  calls,
  start,
  end,
  incidentId,
}: HandoffsDialogProps) {
  const root = calls.find((c) => c.id === ROOT_CALL_ID)
  const steps = handoffSteps(calls, end)
  const byId = new Map(calls.map((c) => [c.id, c]))

  const [picked, setPicked] = useState<Selection | null>(null)
  const fallback: Selection | null = steps[0]
    ? { kind: "brief", callId: steps[0][0].id }
    : root
      ? { kind: "brief", callId: ROOT_CALL_ID }
      : null
  const selection = picked && byId.has(picked.callId) ? picked : fallback
  const selectedCall = selection ? byId.get(selection.callId) : undefined

  const isSelected = (kind: Selection["kind"], callId: string) =>
    selection?.kind === kind && selection.callId === callId
  const select = (kind: Selection["kind"], callId: string) => setPicked({ kind, callId })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          "left-0 top-0 h-screen w-screen max-w-none translate-x-0 translate-y-0",
          "flex flex-col gap-0 overflow-y-auto rounded-none border-0 p-0",
          "sm:max-w-none",
        )}
      >
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-10 py-8">
          <DialogHeader className="gap-1.5">
            <DialogTitle className="text-3xl font-semibold tracking-tight">
              What each agent was handed
            </DialogTitle>
            <DialogDescription className="max-w-3xl text-base">
              The supervisor briefs each specialist and gets an answer back. Specialists never
              see each other's work, only what passes through the supervisor
              {incidentId ? ` · ${incidentId}` : ""}
            </DialogDescription>
          </DialogHeader>

          <section className="rounded-xl border bg-card p-5">
            <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h3 className="font-semibold">Context window</h3>
              <p className="text-sm text-muted-foreground">
                Tokens each agent sent the model on every call: its system prompt, tools, brief
                and everything it has read so far. Click a line to inspect that agent.
              </p>
            </div>
            <ContextChart
              calls={calls}
              start={start}
              end={end}
              height={220}
              selectedId={selection?.kind === "agent" ? selection.callId : null}
              onSelect={(id) => select("agent", id)}
            />
          </section>

          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
            <section className="space-y-4">
              {root && (
                <StepBlock label="Alert">
                  <div className={FLOW_ROW}>
                    <MessageCard
                      from="Incident"
                      icon={<Siren className="size-3.5 text-destructive" />}
                      text={root.brief}
                      pendingLabel="Not recorded on this run"
                      selected={isSelected("brief", ROOT_CALL_ID)}
                      onClick={() => select("brief", ROOT_CALL_ID)}
                    />
                    <Arrow />
                    <AgentNode
                      call={root}
                      selected={isSelected("agent", ROOT_CALL_ID)}
                      onClick={() => select("agent", ROOT_CALL_ID)}
                    />
                    <span />
                    <span />
                  </div>
                </StepBlock>
              )}

              {steps.map((step, i) => (
                <StepBlock
                  key={step[0].id}
                  label={`Step ${i + 1}`}
                  parallel={step.length > 1}
                >
                  {step.map((call) => (
                    <div key={call.id} className={FLOW_ROW}>
                      <MessageCard
                        from="Brief"
                        icon={<SenderIcon direction="in" source="supervisor" />}
                        text={call.context?.prompt ?? call.brief}
                        selected={isSelected("brief", call.id)}
                        onClick={() => select("brief", call.id)}
                      />
                      <Arrow />
                      <AgentNode
                        call={call}
                        selected={isSelected("agent", call.id)}
                        onClick={() => select("agent", call.id)}
                      />
                      <Arrow />
                      <MessageCard
                        from="Answer"
                        icon={<SenderIcon direction="out" source={call.source} />}
                        text={call.returned}
                        summary={
                          call.source === "triage_agent"
                            ? parseTriage(call.returned)?.summary
                            : null
                        }
                        pendingLabel={call.status === "pending" ? "Working…" : "No answer"}
                        selected={isSelected("return", call.id)}
                        onClick={() => select("return", call.id)}
                      />
                    </div>
                  ))}
                </StepBlock>
              ))}

              {root?.returned && (
                <StepBlock label="Close">
                  <div className={FLOW_ROW}>
                    <span />
                    <span />
                    <AgentNode
                      call={root}
                      selected={isSelected("agent", ROOT_CALL_ID)}
                      onClick={() => select("agent", ROOT_CALL_ID)}
                    />
                    <Arrow />
                    <MessageCard
                      from="Summary"
                      icon={<FileText className="size-3.5 text-muted-foreground" />}
                      text={root.returned}
                      selected={isSelected("return", ROOT_CALL_ID)}
                      onClick={() => select("return", ROOT_CALL_ID)}
                    />
                  </div>
                </StepBlock>
              )}
            </section>

            <aside className="rounded-xl border bg-card lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
              {selection && selectedCall ? (
                <Detail selection={selection} call={selectedCall} start={start} />
              ) : (
                <p className="p-5 text-sm text-muted-foreground">Nothing handed over yet.</p>
              )}
            </aside>
          </div>

          <p className="text-xs text-muted-foreground">
            Context sizes are the tokens each model call sent, as the gateway reported them,
            cached reads included. "≈ tokens" next to a handoff is estimated at four characters
            per token.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// brief | → | agent | → | answer
const FLOW_ROW =
  "grid grid-cols-[minmax(0,1fr)_1.25rem_11.5rem_1.25rem_minmax(0,1fr)] items-stretch gap-1.5"

function StepBlock({
  label,
  parallel = false,
  children,
}: {
  label: string
  parallel?: boolean
  children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
        {label}
        {parallel && (
          <span className="rounded-full border px-1.5 py-px tracking-normal normal-case">
            in parallel
          </span>
        )}
        <span className="h-px flex-1 bg-border" />
      </div>
      <div className="relative space-y-2">
        {/* A bracket in the gutter, so parallel rows stay in column. */}
        {parallel && (
          <span className="absolute inset-y-1 -left-3 w-1.5 rounded-l border-y border-l border-dashed border-muted-foreground/50" />
        )}
        {children}
      </div>
    </div>
  )
}

function Arrow() {
  return (
    <span className="flex items-center justify-center text-muted-foreground/60">
      <ArrowRight className="size-4" />
    </span>
  )
}

/** Plain-text preview of a markdown handoff. */
function preview(text: string): string {
  return text
    .replace(/```\w*/g, " ")
    .replace(/^\s*(#+|>)\s*/gm, "")
    .replace(/\*\*|[`|]/g, "")
    .replace(/\s+/g, " ")
    .trim()
}

/** Brief or answer arrow, in the colour of whoever wrote it. */
function SenderIcon({ direction, source }: { direction: "in" | "out"; source: string }) {
  const Icon = direction === "in" ? CornerDownRight : CornerUpLeft
  return <Icon className="size-3.5" style={{ color: sourceStyle(source).accent }} />
}

function MessageCard({
  from,
  icon,
  text,
  summary,
  pendingLabel = "",
  selected,
  onClick,
}: {
  from: string
  icon?: ReactNode
  text?: string
  /** Shown instead of the text's opening when the answer parsed (triage). */
  summary?: string | null
  pendingLabel?: string
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex min-w-0 flex-col gap-1 rounded-lg border bg-card px-3 py-2 text-left transition-colors hover:bg-muted/50",
        selected && "ring-2 ring-primary/70",
      )}
    >
      <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {icon}
        <span className="truncate font-medium tracking-wider uppercase">{from}</span>
        {text && (
          <span className="ml-auto shrink-0 whitespace-nowrap tabular-nums">
            ≈{formatTokens(approxTokens(text))} tok
          </span>
        )}
      </span>
      {text ? (
        <span className="line-clamp-3 text-xs leading-snug text-foreground/85">
          {summary ?? preview(text)}
        </span>
      ) : (
        <span className="text-xs text-muted-foreground italic">{pendingLabel}</span>
      )}
    </button>
  )
}

function AgentNode({
  call,
  selected,
  onClick,
}: {
  call: AgentCall
  selected: boolean
  onClick: () => void
}) {
  const style = sourceStyle(call.source)
  const Icon = style.icon
  const range = contextRange(call)
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex min-w-0 flex-col gap-1.5 rounded-lg border px-3 py-2 text-left transition-colors hover:bg-muted/50",
        selected && "ring-2 ring-primary/70",
      )}
      style={{
        background: `color-mix(in oklab, ${style.accent} 7%, var(--card))`,
        borderColor: `color-mix(in oklab, ${style.accent} 35%, var(--border))`,
      }}
    >
      <span className="flex items-center gap-1.5">
        <span
          className="flex size-5 shrink-0 items-center justify-center rounded"
          style={{
            background: `color-mix(in oklab, ${style.accent} 15%, transparent)`,
            color: style.accent,
          }}
        >
          <Icon className="size-3" />
        </span>
        <span className="truncate text-sm font-semibold">{style.label}</span>
        {call.status === "pending" && <Spinner className="ml-auto size-3 text-muted-foreground" />}
      </span>
      <span className="flex items-center gap-2 text-[11px] text-muted-foreground tabular-nums">
        {range ? (
          <>
            <ContextBars modelCalls={call.modelCalls} accent={style.accent} height={14} barWidth={3} />
            <span>
              {formatTokens(range.first)}
              {range.peak !== range.first && ` → ${formatTokens(range.peak)}`}
            </span>
          </>
        ) : (
          <span>no model calls yet</span>
        )}
        {call.completedAt && (
          <span className="ml-auto">{fmtSeconds(call.completedAt - call.startedAt)}</span>
        )}
      </span>
    </button>
  )
}

function fmtSeconds(ms: number): string {
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

function clock(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

function Party({ source, label }: { source?: string; label?: string }) {
  if (!source) return <span className="font-semibold">{label}</span>
  const style = sourceStyle(source)
  return (
    <span className="font-semibold" style={{ color: style.accent }}>
      {label ?? style.label}
    </span>
  )
}

function Detail({
  selection,
  call,
  start,
}: {
  selection: Selection
  call: AgentCall
  start: number
}) {
  const isRoot = call.id === ROOT_CALL_ID
  const style = sourceStyle(call.source)

  if (selection.kind === "agent") {
    const ctx = call.context
    return (
      <div className="space-y-4 p-5">
        <header className="space-y-1">
          <h3 className="text-lg font-semibold" style={{ color: style.accent }}>
            {style.label}
          </h3>
          <p className="text-sm text-muted-foreground">
            {[
              ctx?.model,
              `${call.modelCalls.length} model call${call.modelCalls.length === 1 ? "" : "s"}`,
              call.completedAt ? fmtSeconds(call.completedAt - call.startedAt) : "running",
              ctx && !isRoot ? priorLabel(ctx.priorMessages) : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </header>
        <AgentContextDetail call={call} systemPromptMaxH="max-h-[28rem]" />
      </div>
    )
  }

  const brief = selection.kind === "brief"
  const prompt = call.context?.prompt
  const text = brief ? (prompt ?? call.brief) : call.returned
  const composed = brief && !isRoot && prompt != null && prompt.trim() !== call.brief.trim()
  const at = brief ? call.startedAt : call.completedAt

  let from: ReactNode
  let to: ReactNode
  if (isRoot) {
    from = brief ? <Party label="PagerDuty incident" /> : <Party source="supervisor" />
    to = brief ? <Party source="supervisor" /> : <Party label="Closing summary" />
  } else {
    from = <Party source={brief ? "supervisor" : call.source} />
    to = <Party source={brief ? call.source : "supervisor"} />
  }

  return (
    <div className="space-y-3 p-5">
      <header className="space-y-1">
        <h3 className="flex flex-wrap items-center gap-2 text-lg">
          {from}
          <ArrowRight className="size-4 text-muted-foreground" />
          {to}
        </h3>
        <p className="text-sm text-muted-foreground">
          {[
            brief ? (isRoot ? "Run prompt" : composed ? "Case file" : "Brief") : "Answer",
            text ? sizeLabel(text) : null,
            at ? `at ${clock(at - start)}` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </header>
      {composed && (
        <p className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          The supervisor wrote only the verdict ({sizeLabel(call.brief)}). The server attached
          the triage, diagnosis and forensics outputs verbatim, so nothing is paraphrased on the
          way to the reporter.
        </p>
      )}
      {text ? (
        brief ? (
          <Markdown content={text} className="text-sm" />
        ) : (
          <ReturnedBody source={isRoot ? "supervisor" : call.source} text={text} />
        )
      ) : (
        <p className="text-sm text-muted-foreground italic">
          {brief ? "Not recorded on this run." : call.status === "pending" ? "Still working…" : "No answer."}
        </p>
      )}
    </div>
  )
}
