import { AlertTriangle, BookOpen, ExternalLink, LineChart, Siren } from "lucide-react"
import { Callout } from "@/components/shared/callout"
import { Chip } from "@/components/shared/chip"
import { CodeBlock } from "@/components/shared/code-block"
import { Expander } from "@/components/shared/expander"
import { KeyValueList } from "@/components/shared/key-value-list"
import { StatusBadge } from "@/components/shared/status-badge"
import { extractAlerts, type PagerDutyAlert } from "@/lib/pagerduty"
import { cn } from "@/lib/utils"
import { JsonView } from "./JsonView"

interface PagerDutyAlertsResultProps {
  content: string
}

/** The tags triage reads the incident's coordinates from, in this order. */
const KEY_TAGS: Record<string, string> = {
  kafka_cluster: "Cluster",
  consumer_group: "Consumer group",
  topic: "Topic",
  connector: "Connector",
}

function clock(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleTimeString("en-GB", { hour12: false })
}

function ExtLink({ href, children }: { href: string | null; children: React.ReactNode }) {
  if (!href) return null
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-md border border-border/70 bg-background px-2 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
    >
      {children}
      <ExternalLink className="size-3 shrink-0" />
    </a>
  )
}

/** The monitor's value against its threshold: the number that paged. */
function ThresholdBar({ alert }: { alert: PagerDutyAlert }) {
  const { value, threshold } = alert
  if (value == null) return null
  const over = threshold != null && value > threshold
  const top = Math.max(value, threshold ?? 0) * 1.2 || 1
  const pct = (n: number) => `${Math.min(100, (n / top) * 100)}%`
  return (
    <div className="rounded-md border border-border/60 bg-card px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-3 text-[11px] text-muted-foreground">
        <span className="truncate font-mono">{alert.metric ?? "value"}</span>
        {alert.window && <span className="shrink-0">{alert.window}</span>}
      </div>
      <div className="mt-1 flex items-center gap-3">
        <span
          className={cn(
            "font-mono text-xl font-semibold tabular-nums",
            over ? "text-destructive" : "text-foreground",
          )}
        >
          {value.toLocaleString("en-US")}
        </span>
        <div className="relative h-2 flex-1 rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full", over ? "bg-destructive" : "bg-primary")}
            style={{ width: pct(value) }}
          />
          {threshold != null && (
            <div
              className="absolute -top-1 -bottom-1 w-0.5 rounded-full bg-foreground/70"
              style={{ left: pct(threshold) }}
              title={`Threshold ${threshold.toLocaleString("en-US")}`}
            />
          )}
        </div>
      </div>
      {threshold != null && (
        <div className="mt-1 text-right text-[11px] text-muted-foreground tabular-nums">
          threshold {threshold.toLocaleString("en-US")}
          {over && (
            <span className="text-destructive">
              {" "}
              · {Math.round(((value - threshold) / threshold) * 100)}% over
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function AlertCard({ alert }: { alert: PagerDutyAlert }) {
  const keyTags = Object.keys(KEY_TAGS).flatMap((k) =>
    alert.tags.filter(([tk]) => tk === k).map(([, v]) => ({ key: KEY_TAGS[k], value: v })),
  )
  const otherTags = alert.tags.filter(([k]) => !(k in KEY_TAGS))
  const time = clock(alert.createdAt)

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {alert.severity && (
          <StatusBadge tone={alert.severity === "critical" ? "destructive" : "warning"}>
            {alert.severity}
          </StatusBadge>
        )}
        {alert.status && <span>{alert.status}</span>}
        {alert.source && <span>· via {alert.source}</span>}
        {time && (
          <span className="tabular-nums" title={alert.createdAt ?? undefined}>
            · {time}
          </span>
        )}
        {alert.htmlUrl && (
          <a
            href={alert.htmlUrl}
            target="_blank"
            rel="noreferrer"
            className="ml-auto inline-flex items-center gap-1 font-mono hover:text-foreground"
            title="Open the alert in PagerDuty"
          >
            {alert.id}
            <ExternalLink className="size-3" />
          </a>
        )}
      </div>

      <Callout
        variant="warning"
        size="sm"
        icon={<AlertTriangle className="size-3.5" />}
        title={alert.summary}
      />

      <ThresholdBar alert={alert} />

      {keyTags.length > 0 && (
        <KeyValueList rows={keyTags.map(({ key, value }) => ({ key, value }))} />
      )}
      {otherTags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {otherTags.map(([k, v]) => (
            <Chip key={k}>
              {k}:{v}
            </Chip>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        <ExtLink href={alert.monitorUrl}>
          <LineChart className="size-3 shrink-0" />
          {alert.monitorName ?? "Monitor"}
          {alert.monitorId && <span className="font-mono">#{alert.monitorId}</span>}
        </ExtLink>
        <ExtLink href={alert.snapshotUrl}>
          <Siren className="size-3 shrink-0" />
          Snapshot
        </ExtLink>
        <ExtLink href={alert.runbookUrl}>
          <BookOpen className="size-3 shrink-0" />
          Runbook
        </ExtLink>
      </div>

      {alert.monitorQuery && (
        <Expander label="Monitor query">
          <CodeBlock className="whitespace-pre-wrap break-all">{alert.monitorQuery}</CodeBlock>
        </Expander>
      )}
    </div>
  )
}

/**
 * ``browse_incidents`` ``list_alerts`` (PagerDuty's hosted MCP): the alerts
 * behind the incident, each with the monitor payload the integration sent -
 * the value that paged against its threshold, the tags triage reads the
 * cluster, group and topic from, and links to the monitor and the runbook.
 */
export function PagerDutyAlertsResult({ content }: PagerDutyAlertsResultProps) {
  const alerts = extractAlerts(content)
  if (alerts.length === 0) return <JsonView content={content} />
  return (
    <div className="space-y-4">
      {alerts.map((alert, i) => (
        <div key={alert.id ?? i} className={cn(i > 0 && "border-t border-border/60 pt-4")}>
          <AlertCard alert={alert} />
        </div>
      ))}
    </div>
  )
}
