import { Check, X } from "lucide-react"
import { Callout } from "@/components/shared/callout"
import { StatGrid, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { StatusDot } from "@/components/shared/status-dot"
import { parseToolResult } from "./parse"
import type { EnvironmentHealthData } from "./types"

interface Props {
  result: string
}

export function EnvironmentHealth({ result }: Props) {
  const parsed = parseToolResult<EnvironmentHealthData>(result, ["environment", "healthy"])
  if (!parsed.ok) return null
  const d = parsed.data
  const tone = d.healthy ? "success" : "destructive"

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <StatusDot tone={tone} size="lg" />
        <div className="flex flex-col gap-1">
          <StatusBadge tone={tone}>
            {d.healthy ? "Healthy" : "Unhealthy"}
          </StatusBadge>
          <span className="font-mono text-xs text-muted-foreground">
            {d.environment}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <StatusDot
            tone={d.agent_connected ? "success" : "destructive"}
            size="sm"
          />
          <span className="text-xs text-muted-foreground">
            Agent {d.agent_connected ? "connected" : "disconnected"}
          </span>
        </div>
      </div>

      {d.summary && (
        <StatGrid cols={4}>
          <StatTile label="Brokers" value={d.summary.kafka_brokers} />
          <StatTile label="Topics" value={d.summary.topics} />
          <StatTile label="Consumers" value={d.summary.consumers} />
          <StatTile label="Connectors" value={d.summary.connectors} />
        </StatGrid>
      )}

      {d.issues && d.issues.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-xs font-medium tracking-wider text-destructive uppercase">
            Issues
          </span>
          {d.issues.map((issue, idx) => (
            <Callout
              key={idx}
              variant="destructive"
              size="sm"
              icon={<X className="size-3" />}
              title={issue}
            />
          ))}
        </div>
      )}

      {(!d.issues || d.issues.length === 0) && d.healthy && (
        <div className="flex items-center gap-1.5 text-xs text-success">
          <Check className="size-3" />
          <span>No issues detected.</span>
        </div>
      )}
    </div>
  )
}
