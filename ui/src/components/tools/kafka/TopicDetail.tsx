import { Chip } from "@/components/shared/chip"
import { CountPill } from "@/components/shared/count-pill"
import { Expander } from "@/components/shared/expander"
import { KeyValueList } from "@/components/shared/key-value-list"
import { Meter } from "@/components/shared/meter"
import { SectionHeader } from "@/components/shared/section-header"
import { StatGrid, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { cn } from "@/lib/utils"
import { extractAvroFields, formatNumber, parseToolResult, tagLabel } from "./parse"
import { AvroSchemaSection } from "./AvroSchema"
import type {
  PartitionMessages,
  TopicConfigEntry,
  TopicDetailData,
} from "./types"

interface Props {
  result: string
}

export function TopicDetail({ result }: Props) {
  const parsed = parseToolResult<TopicDetailData>(result, ["topicName", "partitions"])
  if (!parsed.ok) return null
  const d = parsed.data

  const configs = Array.isArray(d.config) ? d.config : []
  const overrides = configs.filter((c) => !c.isDefault)
  const defaults = configs.filter((c) => c.isDefault)
  const partitions = d.messagesPerPartition ?? []
  const consumers = d.consumers ?? []
  const tags = d.tags ?? []
  const valueFields = extractAvroFields(d.valueSchema)

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="truncate font-mono text-xs font-semibold">{d.topicName}</span>
          {d.isMarkedForDeletion && (
            <StatusBadge tone="destructive">deleting</StatusBadge>
          )}
          {d.isCompacted && <StatusBadge tone="warning">compacted</StatusBadge>}
          {d.isControlTopic && <StatusBadge tone="muted">internal</StatusBadge>}
          {d.valueSchemaVersion != null && (
            <StatusBadge tone="info">schema v{d.valueSchemaVersion}</StatusBadge>
          )}
        </div>
        {d.lrn && (
          <span className="block truncate font-mono text-xs text-muted-foreground">
            {d.lrn}
          </span>
        )}
      </div>

      <StatGrid cols={3}>
        <StatTile label="Partitions" value={String(d.partitions)} />
        <StatTile
          label="Replication"
          value={String(d.replication)}
          tone={d.replication < 2 ? "warning" : undefined}
        />
        <StatTile label="Total msgs" value={formatNumber(d.totalMessages ?? 0)} />
        {d.messagesPerSecond != null && (
          <StatTile
            label="Msgs/sec"
            value={String(d.messagesPerSecond)}
            tone="info"
          />
        )}
        {d.keyType && <StatTile label="Key" value={d.keyType} tone="muted" />}
        {d.valueType && <StatTile label="Value" value={d.valueType} tone="info" />}
      </StatGrid>

      {partitions.length > 0 && <PartitionDistribution partitions={partitions} />}

      {valueFields && valueFields.length > 0 && (
        <AvroSchemaSection fields={valueFields} raw={d.valueSchema ?? ""} />
      )}

      {overrides.length > 0 && (
        <div className="space-y-1.5">
          <SectionHeader
            title={
              <span className="uppercase tracking-wider text-warning">
                Custom config
              </span>
            }
            count={overrides.length}
          />
          <KeyValueList
            rows={overrides.map((c) => ({
              key: <span className="text-warning">{c.name}</span>,
              value: (
                <>
                  {c.defaultValue != null && c.defaultValue !== "" && (
                    <span className="mr-1.5 text-muted-foreground line-through">
                      {c.defaultValue}
                    </span>
                  )}
                  <span className="text-warning">{c.value}</span>
                </>
              ),
              accent: true,
            }))}
          />
        </div>
      )}

      {defaults.length > 0 && (
        <Expander
          label="Default config"
          meta={<CountPill>{defaults.length}</CountPill>}
        >
          <KeyValueList
            rows={defaults.map((c: TopicConfigEntry) => ({
              key: c.name,
              value: c.value,
            }))}
          />
        </Expander>
      )}

      {consumers.length > 0 && (
        <div className="space-y-1">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Consumers
          </span>
          <div className="flex flex-wrap gap-1">
            {consumers.map((c, idx) => {
              const id =
                typeof c === "string" ? c : (c as { id?: string }).id ?? `consumer-${idx}`
              const state =
                typeof c === "object" && c !== null
                  ? (c as { state?: string }).state
                  : undefined
              return (
                <Chip key={`${id}-${idx}`}>
                  {id}
                  {state && <span className="ml-1">({state})</span>}
                </Chip>
              )
            })}
          </div>
        </div>
      )}

      {tags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {tags.map((t, idx) => {
            const label = tagLabel(t)
            if (!label) return null
            return <Chip key={`${label}-${idx}`}>{label}</Chip>
          })}
        </div>
      )}

      {d.description && (
        <p className="text-xs leading-relaxed text-muted-foreground">{d.description}</p>
      )}
    </div>
  )
}

function PartitionDistribution({ partitions }: { partitions: PartitionMessages[] }) {
  const maxMsgs = Math.max(...partitions.map((p) => p.messages), 1)
  const totalMsgs = partitions.reduce((sum, p) => sum + p.messages, 0)
  const avg = totalMsgs / partitions.length
  const hasSkew = partitions.some((p) => Math.abs(p.messages - avg) / Math.max(avg, 1) > 0.5)

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Partition distribution
        </span>
        {hasSkew && <StatusBadge tone="warning">skewed</StatusBadge>}
      </div>
      <div className="space-y-0.5">
        {partitions.map((p) => {
          const deviation = avg > 0 ? ((p.messages - avg) / avg) * 100 : 0
          const isHot = deviation > 30
          return (
            <div key={p.partition} className="flex items-center gap-2">
              <span className="w-6 text-right font-mono text-xs tabular-nums text-muted-foreground">
                {p.partition}
              </span>
              <Meter
                value={p.messages}
                max={maxMsgs}
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
                {formatNumber(p.messages)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
