import { EmptyState } from "@/components/shared/empty-state"
import { Meter } from "@/components/shared/meter"
import { SectionHeader } from "@/components/shared/section-header"
import { StatStrip, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { cn } from "@/lib/utils"
import { parseToolResult, formatNumber, formatBytes } from "./parse"
import type { PartitionDetail, ReplicaInfo, TopicPartitionsData } from "./types"

interface Props {
  result: string
}

interface ParsedReplicas {
  total: number
  inSync: number
}

function parseReplicas(p: PartitionDetail): ParsedReplicas {
  const raw = p.replicas ?? []
  if (raw.length === 0) return { total: 0, inSync: 0 }
  if (typeof raw[0] === "object") {
    const replicas = raw as ReplicaInfo[]
    return {
      total: replicas.length,
      inSync: replicas.filter((r) => r.inSync).length,
    }
  }
  const ids = raw as number[]
  const isr = p.isr ?? []
  return { total: ids.length, inSync: isr.length }
}

export function TopicPartitions({ result }: Props) {
  const parsed = parseToolResult<TopicPartitionsData>(result, ["partitions"])
  if (!parsed.ok) return null
  const d = parsed.data

  if (d.partitions.length === 0) {
    return (
      <div className="space-y-2">
        <SectionHeader title="Partitions" count={0} />
        <EmptyState title="No partition data available." />
      </div>
    )
  }

  const totalMessages = d.partitions.reduce((s, p) => s + (p.messages ?? 0), 0)
  const totalBytes = d.partitions.reduce((s, p) => s + (p.bytes ?? 0), 0)
  const maxMessages = Math.max(...d.partitions.map((p) => p.messages ?? 0), 1)
  const avg = totalMessages / d.partitions.length
  const hasSkew = d.partitions.some(
    (p) => avg > 0 && Math.abs((p.messages ?? 0) - avg) / avg > 0.5,
  )

  const allReplicas = d.partitions.map(parseReplicas)
  const hasIsrIssue = allReplicas.some((r) => r.total > 0 && r.inSync < r.total)

  return (
    <div className="space-y-3">
      <SectionHeader
        title="Partitions"
        count={d.partitions.length}
        end={
          hasSkew || hasIsrIssue ? (
            <>
              {hasSkew && <StatusBadge tone="warning">skewed</StatusBadge>}
              {hasIsrIssue && (
                <StatusBadge tone="destructive">under-replicated</StatusBadge>
              )}
            </>
          ) : undefined
        }
      />

      <StatStrip className="overflow-hidden rounded-md border border-border bg-card">
        <StatTile label="Total msgs" value={formatNumber(totalMessages)} />
        {totalBytes > 0 && (
          <StatTile label="Total size" value={formatBytes(totalBytes)} />
        )}
        <StatTile label="Leader" value={`broker-${d.partitions[0].leader}`} />
      </StatStrip>

      <div className="space-y-1">
        {d.partitions.map((p) => {
          const replicas = parseReplicas(p)
          const isrOk = replicas.total === 0 || replicas.inSync === replicas.total
          const deviation = avg > 0 ? (((p.messages ?? 0) - avg) / avg) * 100 : 0
          const isHot = deviation > 30

          return (
            <div
              key={p.partition}
              className="overflow-hidden rounded-md border border-border bg-card"
            >
              <div className="flex items-center gap-2 px-3 py-1.5">
                <span className="w-6 text-right font-mono text-xs tabular-nums text-muted-foreground">
                  {p.partition}
                </span>
                <Meter
                  value={p.messages ?? 0}
                  max={maxMessages}
                  tone={isHot ? "warning" : "info"}
                  minPct={2}
                  className="h-2 flex-1"
                />
                <span
                  className={cn(
                    "w-12 text-right font-mono text-xs tabular-nums",
                    isHot ? "text-warning" : "text-muted-foreground",
                  )}
                >
                  {formatNumber(p.messages ?? 0)}
                </span>
              </div>
              <StatStrip className="border-t border-border">
                <StatTile label="Leader" value={`${p.leader}`} />
                <StatTile
                  label="ISR"
                  value={`${replicas.inSync}/${replicas.total}`}
                  tone={!isrOk ? "warning" : undefined}
                />
                <StatTile
                  label="Offsets"
                  value={`${formatNumber(p.begin)}..${formatNumber(p.end)}`}
                />
                {p.bytes != null && p.bytes > 0 && (
                  <StatTile label="Size" value={formatBytes(p.bytes)} />
                )}
              </StatStrip>
            </div>
          )
        })}
      </div>
    </div>
  )
}
