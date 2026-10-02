import { useEffect, useMemo, useState, type ComponentType } from "react"
import { Clock, Coins, User } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  ENGINEER_USD_PER_HOUR,
  agentResponse,
  oncallResponse,
  type Response,
  type Step,
} from "@/lib/runSummary"
import { cn } from "@/lib/utils"
import type { StreamState } from "@/lib/types"

interface RunSummaryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  state: StreamState
  incidentId: string | null
}

/**
 * End-of-run summary: the same incident handled by a human on-call team and
 * by the agent, from the alert to a published RCA.
 *
 * - At a glance: total time and total cost, each as two bars on a shared
 *   scale, so the agent's bar is as small as it really is.
 * - Step by step: each response's steps as a timeline on its own scale, with
 *   who does the step, how long it takes and what it costs. The agent's
 *   numbers are measured on the run; the team's are an estimate
 *   (lib/runSummary.ts) and badged as one.
 *
 * Bars grow on open (a width transition keyed off ``revealed``), and replay
 * on every open.
 */

const AGENT_COLOR = "var(--lenses-brand)"
const TEAM_BAR = "bg-muted-foreground/45"

// Step table columns: step | timeline | time | cost.
const STEP_COLS = "grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_4.5rem_4rem] items-center gap-x-3"

function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return "-"
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return s % 60 ? `${m}m ${s % 60}s` : `${m}m`
  const h = Math.floor(m / 60)
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`
}

function fmtUsd(usd: number | null | undefined): string {
  if (usd == null) return "n/a"
  if (usd >= 10) return `$${Math.round(usd).toLocaleString("en-US")}`
  if (usd >= 0.01 || usd === 0) return `$${usd.toFixed(2)}`
  return "<$0.01"
}

/** "33×", or null when there is nothing to compare. */
function ratio(team: number | null, agent: number | null | undefined): string | null {
  if (team == null || agent == null || agent <= 0) return null
  const r = team / agent
  return `${r < 10 ? r.toFixed(1) : Math.round(r).toLocaleString("en-US")}×`
}

export function RunSummaryDialog({
  open,
  onOpenChange,
  state,
  incidentId,
}: RunSummaryDialogProps) {
  // Reset to false (during render) whenever the dialog closes so each open
  // replays the reveal from scratch.
  const [revealed, setRevealed] = useState(false)
  if (!open && revealed) setRevealed(false)
  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => setRevealed(true), 80)
    return () => clearTimeout(t)
  }, [open])

  const team = useMemo(() => oncallResponse(), [])
  const agent = useMemo(() => agentResponse(state), [state])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          // Full screen: override the centered-modal positioning/sizing.
          "left-0 top-0 h-screen w-screen max-w-none translate-x-0 translate-y-0",
          "flex flex-col gap-0 overflow-y-auto rounded-none border-0 p-0",
          "sm:max-w-none",
        )}
      >
        <div className="m-auto flex w-full max-w-7xl flex-col gap-5 px-10 py-8">
          <DialogHeader className="gap-1.5">
            <DialogTitle className="text-3xl font-semibold tracking-tight">
              Same incident, two responses
            </DialogTitle>
            <DialogDescription className="text-base">
              From the alert to a published root-cause analysis
              {incidentId ? ` · ${incidentId}` : ""}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 lg:grid-cols-2">
            <TotalCard
              title="Time to root cause"
              icon={Clock}
              team={team.totalMs}
              agent={agent?.totalMs}
              format={fmtDuration}
              verdict="faster"
              revealed={revealed}
            />
            <TotalCard
              title="Cost of the response"
              icon={Coins}
              team={team.costUsd}
              agent={agent?.costUsd}
              format={fmtUsd}
              verdict="cheaper"
              revealed={revealed}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <StepsPanel
              title="On-call team"
              badge="Estimate"
              response={team}
              variant="team"
              revealed={revealed}
            />
            <StepsPanel
              title="SRE Agent"
              badge="Measured on this run"
              response={agent}
              variant="agent"
              revealed={revealed}
            />
          </div>

          <div className="space-y-1 text-xs leading-relaxed text-muted-foreground">
            <p>
              <span className="font-medium text-foreground">On-call team:</span> an
              estimate for a P1 Kafka incident worked by people, up to four
              engineers at ${ENGINEER_USD_PER_HOUR}/hour fully loaded.
            </p>
            <p>
              <span className="font-medium text-foreground">SRE Agent:</span> measured
              on this run. Wall-clock time from its first event to its last, and
              each model call's tokens at its model's list price, cache reads
              and writes at their own rates.
            </p>
            <p>
              Both end at the same point: root cause found, RCA published,
              channel told. The fix stays a human decision.
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// At a glance
// ---------------------------------------------------------------------------

interface TotalCardProps {
  title: string
  icon: ComponentType<{ className?: string }>
  team: number | null
  agent: number | null | undefined
  format: (v: number | null | undefined) => string
  verdict: string
  revealed: boolean
}

function TotalCard({ title, icon: Icon, team, agent, format, verdict, revealed }: TotalCardProps) {
  const max = Math.max(team ?? 0, agent ?? 0)
  const pct = (v: number | null | undefined) => (v != null && max > 0 ? (v / max) * 100 : 0)
  const times = ratio(team, agent)

  return (
    <section className="rounded-xl border border-border bg-card p-5">
      <header className="flex items-center justify-between gap-4">
        <h3 className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-muted-foreground">
          <Icon className="size-4" />
          {title}
        </h3>
        {times && (
          <span
            className="text-2xl font-semibold tabular-nums"
            style={{
              color: AGENT_COLOR,
              opacity: revealed ? 1 : 0,
              transition: "opacity 400ms ease 900ms",
            }}
          >
            {times} {verdict}
          </span>
        )}
      </header>
      <div className="mt-5 space-y-3">
        <TotalBar
          label="On-call team"
          value={format(team)}
          pct={pct(team)}
          variant="team"
          revealed={revealed}
          delayMs={100}
        />
        <TotalBar
          label="SRE Agent"
          value={format(agent)}
          pct={pct(agent)}
          variant="agent"
          revealed={revealed}
          delayMs={350}
        />
      </div>
    </section>
  )
}

function TotalBar({
  label,
  value,
  pct,
  variant,
  revealed,
  delayMs,
}: {
  label: string
  value: string
  pct: number
  variant: "team" | "agent"
  revealed: boolean
  delayMs: number
}) {
  const agent = variant === "agent"
  return (
    <div className="grid grid-cols-[7rem_minmax(0,1fr)_6.5rem] items-center gap-3">
      <span className="text-sm font-medium">{label}</span>
      <div className="relative h-8 rounded-md bg-muted/50">
        <div
          className={cn("absolute inset-y-0 left-0 rounded-md", !agent && TEAM_BAR)}
          style={{
            // A sliver still has to be visible: that is the point.
            width: revealed ? `max(${pct}%, 6px)` : "0%",
            background: agent ? AGENT_COLOR : undefined,
            transition: "width 900ms cubic-bezier(0.16,1,0.3,1)",
            transitionDelay: `${delayMs}ms`,
          }}
        />
      </div>
      <span
        className="text-right font-mono text-lg font-semibold tabular-nums"
        style={agent ? { color: AGENT_COLOR } : undefined}
      >
        {value}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step by step
// ---------------------------------------------------------------------------

interface StepsPanelProps {
  title: string
  badge: string
  response: Response | null
  variant: "team" | "agent"
  revealed: boolean
}

function StepsPanel({ title, badge, response, variant, revealed }: StepsPanelProps) {
  const agent = variant === "agent"
  const parallel = response ? hasParallelSteps(response.steps) : false

  return (
    <section className="flex flex-col rounded-xl border border-border bg-card p-5">
      <header className="flex items-center justify-between gap-4">
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <span
            className={cn("size-3 rounded-sm", !agent && TEAM_BAR)}
            style={agent ? { background: AGENT_COLOR } : undefined}
          />
          {title}
        </h3>
        <span className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground">
          {badge}
        </span>
      </header>

      {!response ? (
        <p className="mt-6 text-sm text-muted-foreground">No timing data for this run.</p>
      ) : (
        <>
          <div
            className={cn(
              STEP_COLS,
              "mt-4 border-b border-border pb-2 text-[11px] uppercase tracking-wider text-muted-foreground",
            )}
          >
            <span>Step</span>
            <span className="flex justify-between font-mono normal-case tracking-normal">
              <span>0</span>
              <span>{fmtDuration(response.totalMs)}</span>
            </span>
            <span className="text-right">Time</span>
            <span className="text-right">Cost</span>
          </div>

          {response.steps.map((step, i) => (
            <StepRow
              key={step.key}
              step={step}
              totalMs={response.totalMs}
              variant={variant}
              revealed={revealed}
              delayMs={500 + i * 120}
            />
          ))}

          <div className={cn(STEP_COLS, "mt-auto pt-3 text-base font-semibold")}>
            <span>Total</span>
            <span className="text-xs font-normal text-muted-foreground">
              {parallel && "Overlapping bars ran in parallel."}
            </span>
            <span className="text-right font-mono tabular-nums">
              {fmtDuration(response.totalMs)}
            </span>
            <span
              className="text-right font-mono tabular-nums"
              style={agent ? { color: AGENT_COLOR } : undefined}
            >
              {fmtUsd(response.costUsd)}
            </span>
          </div>
        </>
      )}
    </section>
  )
}

function StepRow({
  step,
  totalMs,
  variant,
  revealed,
  delayMs,
}: {
  step: Step
  totalMs: number
  variant: "team" | "agent"
  revealed: boolean
  delayMs: number
}) {
  const agent = variant === "agent"
  const pct = (ms: number) => (totalMs > 0 ? (ms / totalMs) * 100 : 0)

  return (
    <div
      className={cn(STEP_COLS, "border-b border-border/50 py-2.5")}
      style={{
        opacity: revealed ? 1 : 0,
        transition: "opacity 300ms ease",
        transitionDelay: `${delayMs}ms`,
      }}
    >
      <div className="min-w-0">
        <div className="text-sm font-medium leading-snug">{step.label}</div>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
          {step.engineers != null && (
            <span className="flex shrink-0" aria-label={`${step.engineers} engineers`}>
              {Array.from({ length: step.engineers }, (_, k) => (
                <User key={k} className="-mr-0.5 size-3.5" />
              ))}
            </span>
          )}
          <span className="leading-snug">{step.who}</span>
        </div>
      </div>

      <div className="relative h-5 rounded bg-muted/40">
        {step.segments.map((seg, k) => (
          <div
            key={k}
            className={cn(
              "absolute rounded",
              step.throughout ? "top-1/2 h-1.5 -translate-y-1/2 opacity-60" : "inset-y-0",
              !agent && TEAM_BAR,
            )}
            style={{
              left: `${pct(seg.start)}%`,
              width: revealed ? `max(${pct(seg.end - seg.start)}%, 3px)` : "0%",
              background: agent ? AGENT_COLOR : undefined,
              transition: "width 700ms cubic-bezier(0.16,1,0.3,1)",
              transitionDelay: `${delayMs}ms`,
            }}
          />
        ))}
      </div>

      {step.throughout ? (
        <span className="whitespace-nowrap text-right text-xs text-muted-foreground">
          whole run
        </span>
      ) : (
        <span className="text-right font-mono text-sm tabular-nums">
          {fmtDuration(step.durationMs)}
        </span>
      )}
      <span className="text-right font-mono text-sm tabular-nums">{fmtUsd(step.costUsd)}</span>
    </div>
  )
}

/** Whether two stages (not the always-on supervisor) overlap in time. */
function hasParallelSteps(steps: Step[]): boolean {
  const segs = steps.filter((s) => !s.throughout).flatMap((s) => s.segments.map((g) => ({ ...g, key: s.key })))
  return segs.some((a, i) =>
    segs.some((b, j) => j > i && a.key !== b.key && a.start < b.end && b.start < a.end),
  )
}
