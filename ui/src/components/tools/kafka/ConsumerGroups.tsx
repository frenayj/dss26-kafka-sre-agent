import { EmptyState } from "@/components/shared/empty-state"
import { Meter } from "@/components/shared/meter"
import { SectionHeader } from "@/components/shared/section-header"
import { StatStrip, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { StatusDot } from "@/components/shared/status-dot"
import { TONE_TEXT } from "@/components/shared/tone"
import { cn } from "@/lib/utils"
import { formatNumber, lagToTone, parseArrayToolResult, stateToTone } from "./parse"
import type { ConsumerGroupItem } from "./types"

interface Props {
  result: string
}

function stateBadgeLabel(state: string, active?: boolean): string {
  const s = state.toLowerCase()
  if (s === "stable") return active ? "Stable" : "Stable (idle)"
  if (s === "rebalancing") return "Rebalancing"
  if (s.includes("noactive") || s === "empty") return "Inactive"
  if (s === "dead") return "Dead"
  return state
}

export function ConsumerGroups({ result }: Props) {
  const parsed = parseArrayToolResult<ConsumerGroupItem>(result)
  if (!parsed.ok) return null
  const groups = parsed.data

  if (groups.length === 0) {
    return (
      <div className="space-y-2">
        <SectionHeader title="Consumer groups" count={0} />
        <EmptyState title="No consumer groups found." />
      </div>
    )
  }

  const globalMaxLag = Math.max(...groups.map((g) => g.maxLag ?? 0), 1)

  return (
    <div className="space-y-2.5">
      <SectionHeader title="Consumer groups" count={groups.length} />

      <div className="space-y-2">
        {groups.map((group) => {
          const maxLag = group.maxLag ?? 0
          const minLag = group.minLag ?? 0
          const lagTone = lagToTone(maxLag)
          const consumerCount = group.consumersCount ?? group.consumers?.length ?? 0
          const partitionCount = group.topicPartitionsCount ?? 0

          return (
            <div
              key={group.id}
              className="overflow-hidden rounded-md border border-border bg-card"
            >
              <div className="flex items-center gap-2 px-3 py-2">
                <StatusDot tone={group.active ? "info" : "muted"} size="sm" />
                <span className="min-w-0 flex-1 truncate font-mono text-xs font-medium">
                  {group.id}
                </span>
                <StatusBadge tone={stateToTone(group.state)} className="shrink-0">
                  {stateBadgeLabel(group.state, group.active)}
                </StatusBadge>
              </div>

              <div className="px-3 pb-2">
                <div className="flex items-center gap-2">
                  <Meter
                    value={maxLag}
                    max={globalMaxLag}
                    tone={lagTone}
                    minPct={2}
                    className="h-2 flex-1"
                  />
                  <span
                    className={cn(
                      "w-14 text-right font-mono text-xs font-medium tabular-nums",
                      TONE_TEXT[lagTone],
                    )}
                  >
                    {formatNumber(maxLag)}
                  </span>
                </div>
              </div>

              <StatStrip className="border-t border-border">
                {minLag !== maxLag && (
                  <StatTile label="Min lag" value={formatNumber(minLag)} />
                )}
                <StatTile
                  label={minLag !== maxLag ? "Max lag" : "Lag"}
                  value={formatNumber(maxLag)}
                />
                <StatTile label="Consumers" value={String(consumerCount)} />
                {partitionCount > 0 && (
                  <StatTile label="Partitions" value={String(partitionCount)} />
                )}
                {group.coordinator && (
                  <StatTile
                    label="Coordinator"
                    value={`broker-${group.coordinator.id}`}
                  />
                )}
              </StatStrip>
            </div>
          )
        })}
      </div>
    </div>
  )
}
