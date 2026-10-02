import { ArrowUpRight, Bot, Boxes, Cable, ExternalLink, FileJson, Gauge } from "lucide-react"
import { GitHubLogo, PagerDutyLogo } from "@/components/icons/brands"
import { StatusBadge } from "@/components/shared/status-badge"
import { StatusDot } from "@/components/shared/status-dot"
import type { Tone } from "@/components/shared/tone"
import { stateToTone } from "@/components/tools/kafka/parse"
import type { IncidentStatus, RunSummary } from "@/lib/api"
import {
  formatDuration,
  type OpsAgent,
  type OpsConnector,
  type OpsConnectors,
  type OpsConsumer,
  type OpsContainer,
  type OpsCulprit,
  type OpsGitHub,
  type OpsPagerDuty,
  type OpsSchema,
  type OpsSection,
  type OpsStack,
  type OpsStatus,
} from "@/lib/ops"
import { LAG_SAMPLES } from "./hooks"
import { Sparkline } from "./Sparkline"
import { StatusCard } from "./StatusCard"

/** Lag at or above this turns the consumer card red. */
const LAG_THRESHOLD = 100
/** Queue rows shown on the agent card before "+N more". */
const MAX_QUEUE_ROWS = 4

/** The section's data, or null while it is missing or its check failed. */
function dataOf<T>(section: OpsSection<T> | undefined): T | null {
  return section && section.error === null ? section : null
}

/** Label/value line for the cards' key facts. */
function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 text-xs">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="flex min-w-0 items-center justify-end gap-1.5 truncate">{children}</span>
    </div>
  )
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>
}

function DashboardLink() {
  return (
    <a href="#/" className="inline-flex items-center gap-0.5 hover:text-foreground">
      Dashboard
      <ArrowUpRight className="size-3" />
    </a>
  )
}

// ---------------------------------------------------------------------------
// PagerDuty
// ---------------------------------------------------------------------------

function pagerDutyTone(d: OpsPagerDuty | null): Tone {
  if (!d || !d.enabled) return "muted"
  if (d.incidents.some((i) => i.status === "triggered")) return "destructive"
  return d.incidents.length > 0 ? "warning" : "success"
}

function PagerDutyCard({ section, now }: { section?: OpsSection<OpsPagerDuty>; now: number }) {
  const d = dataOf(section)
  return (
    <StatusCard
      title="PagerDuty"
      icon={<PagerDutyLogo className="text-brand-pagerduty" />}
      section={section}
      tone={pagerDutyTone(d)}
      now={now}
    >
      {d && !d.enabled && <Muted>PagerDuty not configured (stub mode)</Muted>}
      {d?.enabled && d.incidents.length === 0 && <Muted>No open incidents</Muted>}
      {d?.enabled && d.incidents.length > 0 && (
        <ul className="space-y-1.5">
          {d.incidents.map((inc) => (
            <li key={inc.id} className="flex min-w-0 items-center gap-2 text-xs">
              <StatusBadge tone={inc.status === "triggered" ? "destructive" : "warning"}>
                {inc.status}
              </StatusBadge>
              {inc.url ? (
                <a
                  href={inc.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group/link flex min-w-0 flex-1 items-center gap-1 hover:underline"
                  title={inc.title ?? inc.id}
                >
                  <span className="truncate">{inc.title ?? inc.id}</span>
                  <ExternalLink className="size-3 shrink-0 text-muted-foreground group-hover/link:text-foreground" />
                </a>
              ) : (
                <span className="min-w-0 flex-1 truncate" title={inc.title ?? inc.id}>
                  {inc.title ?? inc.id}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </StatusCard>
  )
}

// ---------------------------------------------------------------------------
// Agent
// ---------------------------------------------------------------------------

const INCIDENT_TONE: Record<IncidentStatus, Tone> = {
  pending: "warning",
  in_progress: "info",
  completed: "success",
}

const RUN_TONE: Record<RunSummary["status"], Tone> = {
  running: "info",
  done: "success",
  error: "destructive",
  cancelled: "muted",
}

function agentTone(d: OpsAgent | null): Tone {
  if (!d) return "muted"
  if (d.last_run?.status === "error") return "destructive"
  if (d.last_run?.status === "running" || d.incidents.some((i) => i.status !== "completed")) {
    return "warning"
  }
  return "success"
}

function AgentCard({ section, now }: { section?: OpsSection<OpsAgent>; now: number }) {
  const d = dataOf(section)
  const run = d?.last_run ?? null
  return (
    <StatusCard
      title="Agent"
      icon={<Bot />}
      section={section}
      tone={agentTone(d)}
      now={now}
      footer={<DashboardLink />}
    >
      {d && (
        <>
          <div className="text-[10px] font-medium tracking-wider text-muted-foreground uppercase">
            Queue
          </div>
          {d.incidents.length === 0 ? (
            <Muted>Queue empty</Muted>
          ) : (
            <ul className="space-y-1.5">
              {d.incidents.slice(0, MAX_QUEUE_ROWS).map((inc) => (
                <li key={inc.id} className="flex min-w-0 items-center gap-2 text-xs">
                  <StatusBadge tone={INCIDENT_TONE[inc.status]}>
                    {inc.status.replace("_", " ")}
                  </StatusBadge>
                  <span className="min-w-0 flex-1 truncate" title={inc.title ?? inc.id}>
                    {inc.title ?? inc.id}
                  </span>
                </li>
              ))}
              {d.incidents.length > MAX_QUEUE_ROWS && (
                <li className="text-xs text-muted-foreground">
                  +{d.incidents.length - MAX_QUEUE_ROWS} more
                </li>
              )}
            </ul>
          )}
          <div className="mt-1 text-[10px] font-medium tracking-wider text-muted-foreground uppercase">
            Last run
          </div>
          {run ? (
            <div className="space-y-1">
              <Fact label="Status">
                <StatusBadge tone={RUN_TONE[run.status]}>{run.status}</StatusBadge>
              </Fact>
              <Fact label="Incident">
                <span className="truncate font-mono">{run.incident_id}</span>
              </Fact>
              <Fact label="Tool calls">
                <span className="font-mono tabular-nums">{run.tool_call_count}</span>
              </Fact>
              <Fact label="Duration">
                <span className="font-mono tabular-nums">
                  {formatDuration((run.ended_at ?? now) - run.started_at)}
                </span>
              </Fact>
            </div>
          ) : (
            <Muted>No runs yet</Muted>
          )}
        </>
      )}
    </StatusCard>
  )
}

// ---------------------------------------------------------------------------
// Consumer lag
// ---------------------------------------------------------------------------

function lagTone(d: OpsConsumer | null): Tone {
  if (!d) return "muted"
  return d.lag < LAG_THRESHOLD ? "success" : "destructive"
}

function ConsumerCard({
  section,
  history,
  now,
}: {
  section?: OpsSection<OpsConsumer>
  history: number[]
  now: number
}) {
  const d = dataOf(section)
  const tone = lagTone(d)
  return (
    <StatusCard
      title="Consumer lag"
      icon={<Gauge />}
      section={section}
      tone={tone}
      now={now}
    >
      {d && (
        <>
          <div className="flex items-end justify-between gap-3">
            <div className="min-w-0">
              <div className="text-4xl leading-none font-semibold">{d.lag.toLocaleString()}</div>
              <div className="mt-1 text-xs text-muted-foreground">messages behind</div>
            </div>
            <StatusBadge tone={d.active ? "success" : "warning"}>
              {d.active ? "active" : "no members"}
            </StatusBadge>
          </div>
          <Sparkline
            values={history}
            capacity={LAG_SAMPLES}
            threshold={LAG_THRESHOLD}
            tone={tone === "muted" ? "success" : tone}
            label="Consumer lag"
            className="h-10"
          />
          <p className="truncate font-mono text-[11px] text-muted-foreground" title={d.group}>
            {d.group}
          </p>
        </>
      )}
    </StatusCard>
  )
}

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

function SchemaCard({ section, now }: { section?: OpsSection<OpsSchema>; now: number }) {
  const d = dataOf(section)
  const broken = d?.compatibility === "NONE"
  return (
    <StatusCard
      title="Schema"
      icon={<FileJson />}
      section={section}
      tone={!d ? "muted" : broken ? "destructive" : "success"}
      now={now}
    >
      {d && (
        <div className="space-y-1.5">
          <p className="truncate font-mono text-xs" title={d.subject}>
            {d.subject}
          </p>
          <Fact label="Latest version">
            <span className="font-mono tabular-nums">v{d.version}</span>
            <span className="font-mono text-muted-foreground tabular-nums">id {d.id}</span>
          </Fact>
          <Fact label="Compatibility">
            <StatusBadge tone={broken ? "destructive" : "success"}>{d.compatibility}</StatusBadge>
          </Fact>
        </div>
      )}
    </StatusCard>
  )
}

// ---------------------------------------------------------------------------
// Connectors
// ---------------------------------------------------------------------------

/** The worst of the connector's own state and its tasks': the connector can
 *  report RUNNING while every task is dead. */
function connectorState(c: OpsConnector): string {
  if (c.tasks.includes("FAILED")) return "FAILED"
  return c.state ?? "UNKNOWN"
}

function connectorsTone(d: OpsConnectors | null): Tone {
  if (!d) return "muted"
  const states = d.connectors.map(connectorState)
  if (states.includes("FAILED")) return "destructive"
  if (states.length === 0 || states.some((s) => s !== "RUNNING")) return "warning"
  return "success"
}

function ConnectorsCard({ section, now }: { section?: OpsSection<OpsConnectors>; now: number }) {
  const d = dataOf(section)
  return (
    <StatusCard
      title="Connectors"
      icon={<Cable />}
      section={section}
      tone={connectorsTone(d)}
      now={now}
    >
      {d && d.connectors.length === 0 && <Muted>No connectors deployed</Muted>}
      {d && d.connectors.length > 0 && (
        <ul className="space-y-2">
          {d.connectors.map((c) => (
            <li key={c.name} className="min-w-0 space-y-1">
              <div className="flex min-w-0 items-center gap-2">
                <StatusDot tone={stateToTone(connectorState(c))} size="sm" />
                <span className="min-w-0 flex-1 truncate font-mono text-xs" title={c.name}>
                  {c.name}
                </span>
                <StatusBadge tone={stateToTone(c.state ?? "")}>{c.state ?? "unknown"}</StatusBadge>
              </div>
              {c.tasks.length > 0 && (
                <div className="flex flex-wrap items-center gap-1 pl-3.5">
                  <span className="text-[10px] text-muted-foreground">tasks</span>
                  {c.tasks.map((t, i) => (
                    <StatusBadge key={i} tone={stateToTone(t)} className="text-[9px]">
                      {t}
                    </StatusBadge>
                  ))}
                </div>
              )}
              {c.error && (
                <p
                  className="ml-3.5 line-clamp-2 font-mono text-[11px] leading-snug break-words text-destructive"
                  title={c.error}
                >
                  {c.error}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </StatusCard>
  )
}

// ---------------------------------------------------------------------------
// GitHub
// ---------------------------------------------------------------------------

const CULPRIT_STATE: Record<OpsCulprit["state"], { label: string; tone: Tone }> = {
  applied: { label: "merged on main", tone: "destructive" },
  pending: { label: "not merged", tone: "success" },
  conflict: { label: "conflict", tone: "warning" },
}

function gitHubTone(d: OpsGitHub | null): Tone {
  if (!d || !d.enabled) return "muted"
  if (d.culprits.some((c) => c.state === "applied")) return "destructive"
  if (d.culprits.some((c) => c.state === "conflict")) return "warning"
  return "success"
}

function GitHubCard({ section, now }: { section?: OpsSection<OpsGitHub>; now: number }) {
  const d = dataOf(section)
  return (
    <StatusCard
      title="GitHub"
      icon={<GitHubLogo className="text-brand-github" />}
      section={section}
      tone={gitHubTone(d)}
      now={now}
    >
      {d && !d.enabled && <Muted>GitHub in stub mode - the agent reads a snapshot</Muted>}
      {d?.enabled && d.culprits.length === 0 && <Muted>No culprit PRs found</Muted>}
      {d?.enabled && d.culprits.length > 0 && (
        <ul className="space-y-2">
          {d.culprits.map((c) => {
            const state = CULPRIT_STATE[c.state]
            return (
              <li key={`${c.scenario}-${c.repo}`} className="min-w-0 space-y-0.5">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-xs font-medium">{c.scenario}</span>
                  <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
                </div>
                <a
                  href={`https://github.com/${c.repo}`}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate font-mono text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                  title={c.title}
                >
                  {c.repo}
                </a>
              </li>
            )
          })}
        </ul>
      )}
    </StatusCard>
  )
}

// ---------------------------------------------------------------------------
// Stack
// ---------------------------------------------------------------------------

/** Why a container needs attention, or null when it is fine. One-shot
 *  services are fine once they exit 0; "starting" is a transient amber. */
function containerProblem(c: OpsContainer): { label: string; tone: Tone } | null {
  if (c.health === "unhealthy") return { label: "unhealthy", tone: "destructive" }
  if (c.state !== "running") {
    if (c.one_shot && c.status.startsWith("Exited (0)")) return null
    return { label: c.state, tone: "destructive" }
  }
  if (c.health === "starting") return { label: "starting", tone: "warning" }
  return null
}

function StackCard({ section, now }: { section?: OpsSection<OpsStack>; now: number }) {
  const d = dataOf(section)
  const services = d?.containers.filter((c) => !c.one_shot) ?? []
  const running = services.filter((c) => c.state === "running").length
  const problems = (d?.containers ?? []).flatMap((c) => {
    const problem = containerProblem(c)
    return problem ? [{ container: c, ...problem }] : []
  })

  let tone: Tone = "muted"
  if (d) {
    if (d.containers.length === 0 || problems.some((p) => p.tone === "destructive")) {
      tone = "destructive"
    } else {
      tone = problems.length > 0 ? "warning" : "success"
    }
  }

  return (
    <StatusCard title="Stack" icon={<Boxes />} section={section} tone={tone} now={now}>
      {d && d.containers.length === 0 && <Muted>No containers - is the stack up?</Muted>}
      {d && d.containers.length > 0 && (
        <>
          <p className="text-sm">
            <span className="font-semibold tabular-nums">
              {running}/{services.length}
            </span>{" "}
            <span className="text-muted-foreground">services running</span>
          </p>
          {problems.length === 0 ? (
            <Muted>All services up</Muted>
          ) : (
            <ul className="space-y-1.5">
              {problems.map(({ container: c, label, tone: problemTone }) => (
                <li key={c.name} className="min-w-0 space-y-0.5">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="min-w-0 flex-1 truncate font-mono text-xs" title={c.name}>
                      {c.service || c.name}
                    </span>
                    <StatusBadge tone={problemTone}>{label}</StatusBadge>
                  </div>
                  <p className="truncate text-[11px] text-muted-foreground" title={c.status}>
                    {c.status}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </StatusCard>
  )
}

// ---------------------------------------------------------------------------
// Board
// ---------------------------------------------------------------------------

interface StatusBoardProps {
  status: OpsStatus | null
  lagHistory: number[]
  now: number
}

export function StatusBoard({ status, lagHistory, now }: StatusBoardProps) {
  return (
    <section
      aria-label="Status"
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
    >
      <PagerDutyCard section={status?.pagerduty} now={now} />
      <AgentCard section={status?.agent} now={now} />
      <ConsumerCard section={status?.consumer} history={lagHistory} now={now} />
      <SchemaCard section={status?.schema} now={now} />
      <ConnectorsCard section={status?.connectors} now={now} />
      <GitHubCard section={status?.github} now={now} />
      <StackCard section={status?.stack} now={now} />
    </section>
  )
}
