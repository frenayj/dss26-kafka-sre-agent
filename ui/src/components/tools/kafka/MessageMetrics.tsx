import { useMemo } from "react"
import { CountPill } from "@/components/shared/count-pill"
import { EmptyState } from "@/components/shared/empty-state"
import { SectionHeader } from "@/components/shared/section-header"
import { StatGrid, StatStrip, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { parseArrayToolResult, formatNumber } from "./parse"
import type { MessageMetricPoint } from "./types"

interface Props {
  result: string
}

function getMessages(p: MessageMetricPoint): number {
  return p.messagesCount ?? p.messages ?? 0
}

function formatShort(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
  } catch {
    return iso
  }
}
function formatFull(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    })
  } catch {
    return iso
  }
}

export function MessageMetrics({ result }: Props) {
  const parsed = parseArrayToolResult<MessageMetricPoint>(result)
  if (!parsed.ok) return null
  const metrics = parsed.data

  if (metrics.length === 0) {
    return (
      <div className="space-y-2">
        <SectionHeader title="Message metrics" />
        <EmptyState title="No message metrics available." />
      </div>
    )
  }

  if (metrics.length < 3) {
    const latest = metrics[metrics.length - 1]
    return (
      <div className="space-y-2">
        <SectionHeader title="Message metrics" />
        <StatGrid cols={2}>
          <StatTile label="Date" value={formatFull(latest.date)} />
          <StatTile
            label="Messages"
            value={formatNumber(getMessages(latest))}
            tone="info"
          />
        </StatGrid>
      </div>
    )
  }

  return <Chart metrics={metrics} />
}

function Chart({ metrics }: { metrics: MessageMetricPoint[] }) {
  const data = useMemo(
    () =>
      metrics.map((m) => ({
        date: m.date,
        label: formatShort(m.date),
        messages: getMessages(m),
      })),
    [metrics],
  )

  const first = data[0]
  const latest = data[data.length - 1]
  const values = data.map((d) => d.messages)
  const maxVal = Math.max(...values)
  const minVal = Math.min(...values)
  const avg = values.reduce((s, v) => s + v, 0) / values.length
  const trend = latest.messages - first.messages
  const trendPct = first.messages > 0 ? ((trend / first.messages) * 100).toFixed(1) : "0"

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold">Message metrics</span>
          <CountPill>{data.length} days</CountPill>
        </div>
        <StatusBadge
          tone={trend >= 0 ? "success" : "destructive"}
          className="font-mono tabular-nums"
        >
          {trend >= 0 ? "+" : ""}
          {trendPct}%
        </StatusBadge>
      </div>

      <StatStrip className="overflow-hidden rounded-md border border-border">
        <StatTile
          label="Latest"
          value={formatNumber(latest.messages)}
          tone="info"
        />
        <StatTile label="Average" value={formatNumber(Math.round(avg))} />
        <StatTile label="Peak" value={formatNumber(maxVal)} />
        <StatTile label="Low" value={formatNumber(minVal)} />
      </StatStrip>

      <Sparkline values={values} />

      <div className="flex justify-between">
        <span className="font-mono text-[10px] text-muted-foreground">
          {formatFull(first.date)}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">
          {formatFull(latest.date)}
        </span>
      </div>
    </div>
  )
}

/**
 * Lightweight inline-SVG area-chart-ish sparkline. Bypasses `recharts` (~50KB
 * gzipped) because the chart is a single-series time series with no
 * interactions beyond hover tooltips, which a real chart lib is overkill for.
 */
function Sparkline({ values }: { values: number[] }) {
  const w = 400
  const h = 80
  const pad = 4
  const maxV = Math.max(...values, 1)
  const minV = Math.min(...values, 0)
  const range = maxV - minV || 1
  const stepX = values.length > 1 ? (w - pad * 2) / (values.length - 1) : 0
  const yFor = (v: number) => h - pad - ((v - minV) / range) * (h - pad * 2)

  const points = values.map((v, i) => `${pad + i * stepX},${yFor(v)}`).join(" ")
  const areaPath =
    values.length > 0
      ? `M ${pad},${h - pad} L ${points
          .split(" ")
          .join(" L ")} L ${pad + (values.length - 1) * stepX},${h - pad} Z`
      : ""

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="w-full h-24"
      aria-hidden
    >
      <defs>
        <linearGradient id="msg-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--info)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--info)" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#msg-grad)" />
      <polyline
        points={points}
        fill="none"
        stroke="var(--info)"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
