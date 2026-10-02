import { EmptyState } from "@/components/shared/empty-state"
import { SectionHeader } from "@/components/shared/section-header"
import { StatStrip, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { StatusDot } from "@/components/shared/status-dot"
import type { Tone } from "@/components/shared/tone"
import { cn } from "@/lib/utils"
import { parseArrayToolResult, formatBytes, formatNumber } from "./parse"
import type { EnvironmentItem } from "./types"

interface Props {
  result: string
}

/**
 * Tier → semantic tone. Production deserves attention (not "error" red),
 * staging is informational, dev/sandbox are low-stakes.
 */
const TIER_TONES: Record<string, Tone> = {
  production: "warning",
  staging: "info",
  development: "muted",
  sandbox: "muted",
}

function tierTone(tier?: string): Tone {
  if (!tier) return "muted"
  return TIER_TONES[tier.toLowerCase()] ?? "muted"
}

function formatDuration(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(1)}µs`
  if (ms < 1000) return `${ms.toFixed(1)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export function EnvironmentList({ result }: Props) {
  const parsed = parseArrayToolResult<EnvironmentItem>(result)
  if (!parsed.ok) return null
  const envs = parsed.data

  return (
    <div className="space-y-2.5">
      <SectionHeader title="Environments" count={envs.length} />

      {envs.length === 0 ? (
        <EmptyState title="No environments configured." />
      ) : (
        <div className="space-y-2">
          {envs.map((env) => (
            <EnvironmentCard key={env.id || env.name} env={env} />
          ))}
        </div>
      )}
    </div>
  )
}

function EnvironmentCard({ env }: { env: EnvironmentItem }) {
  const connected = env.status?.agent_connected ?? false
  const metrics = env.status?.agent?.metrics
  const agent = env.status?.agent?.agent
  const roundtrip = env.status?.agent?.roundtrip_duration
  const connectedAt = env.status?.agent?.connected_at

  return (
    <div className="overflow-hidden rounded-md border border-border bg-card">
      <div className="flex items-center gap-2.5 px-3 py-2">
        <StatusDot tone={connected ? "success" : "destructive"} />
        <div className="flex min-w-0 flex-1 items-baseline gap-2">
          <span className="truncate text-xs font-semibold">
            {env.display_name || env.name}
          </span>
          {env.display_name && env.display_name !== env.name && (
            <span className="truncate font-mono text-xs text-muted-foreground">
              {env.name}
            </span>
          )}
        </div>
        {env.tier && (
          <StatusBadge tone={tierTone(env.tier)}>{env.tier}</StatusBadge>
        )}
        <span
          className={cn(
            "text-xs",
            connected ? "text-success" : "text-destructive",
          )}
        >
          {connected ? "Connected" : "Disconnected"}
        </span>
      </div>

      {connected && metrics && (
        <StatStrip className="border-t border-border">
          {metrics.kafka?.num_brokers != null && (
            <StatTile
              label="Brokers"
              value={formatNumber(metrics.kafka.num_brokers)}
            />
          )}
          {metrics.data?.num_topics != null && (
            <StatTile
              label="Topics"
              value={formatNumber(metrics.data.num_topics)}
            />
          )}
          {metrics.apps?.num_consumers != null && (
            <StatTile
              label="Consumers"
              value={formatNumber(metrics.apps.num_consumers)}
            />
          )}
          {metrics.connect?.num_connectors != null && (
            <StatTile
              label="Connectors"
              value={formatNumber(metrics.connect.num_connectors)}
            />
          )}
        </StatStrip>
      )}

      {connected && metrics?.data && (
        <StatStrip className="border-t border-border">
          {metrics.data.data_in_bytes_per_sec != null && (
            <StatTile
              label="In/s"
              value={formatBytes(metrics.data.data_in_bytes_per_sec)}
            />
          )}
          {metrics.data.data_out_bytes_per_sec != null && (
            <StatTile
              label="Out/s"
              value={formatBytes(metrics.data.data_out_bytes_per_sec)}
            />
          )}
          {metrics.data.data_in_messages_per_sec != null && (
            <StatTile
              label="Msg/s"
              value={formatNumber(metrics.data.data_in_messages_per_sec)}
            />
          )}
          {metrics.data.topic_data_total_bytes != null && (
            <StatTile
              label="Total"
              value={formatBytes(metrics.data.topic_data_total_bytes)}
            />
          )}
        </StatStrip>
      )}

      {connected && (agent || roundtrip != null || connectedAt) && (
        <div className="flex items-center gap-3 border-t border-border bg-background/60 px-3 py-1.5">
          {agent?.version && (
            <span className="text-[10px] text-muted-foreground">v{agent.version}</span>
          )}
          {agent?.hostname && (
            <span className="truncate font-mono text-[10px] text-muted-foreground">
              {agent.hostname}
            </span>
          )}
          {roundtrip != null && (
            <span className="text-[10px] text-muted-foreground">
              RTT {formatDuration(roundtrip * 1000)}
            </span>
          )}
          {connectedAt && (
            <span className="ml-auto text-[10px] text-muted-foreground">
              connected {timeAgo(connectedAt)}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
