import { Chip } from "@/components/shared/chip"
import { StatGrid, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { extractAvroFields, parseToolResult, tagLabel, type TopicTag } from "./parse"
import { AvroSchemaSection } from "./AvroSchema"

interface Props {
  result: string
}

interface TopicMetadataData {
  topicName: string
  lrn?: string | null
  keyType?: string | null
  valueType?: string | null
  keySchema?: string | null
  keySchemaVersion?: number | null
  valueSchema?: string | null
  valueSchemaVersion?: number | null
  description?: string | null
  tags?: TopicTag[] | null
  coverage?: string | null
}

export function TopicMetadata({ result }: Props) {
  const parsed = parseToolResult<TopicMetadataData>(result, ["topicName"])
  if (!parsed.ok) return null
  const d = parsed.data

  const tags = d.tags ?? []
  const valueFields = extractAvroFields(d.valueSchema)

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="truncate font-mono text-xs font-semibold">
            {d.topicName}
          </span>
          {d.valueSchemaVersion != null && (
            <StatusBadge tone="info">schema v{d.valueSchemaVersion}</StatusBadge>
          )}
          {d.coverage && <StatusBadge tone="muted">{d.coverage}</StatusBadge>}
        </div>
        {d.lrn && (
          <span className="block truncate font-mono text-xs text-muted-foreground">
            {d.lrn}
          </span>
        )}
      </div>

      {(d.keyType || d.valueType) && (
        <StatGrid cols={2}>
          {d.keyType && <StatTile label="Key" value={d.keyType} tone="muted" />}
          {d.valueType && <StatTile label="Value" value={d.valueType} tone="info" />}
        </StatGrid>
      )}

      {d.description && (
        <div className="rounded-md border border-border/50 bg-card/30 px-2.5 py-2">
          <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
            {d.description}
          </p>
        </div>
      )}

      {tags.length > 0 && (
        <div className="space-y-1">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Tags
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            {tags.map((t, idx) => {
              const label = tagLabel(t)
              if (!label) return null
              return <Chip key={`${label}-${idx}`}>{label}</Chip>
            })}
          </div>
        </div>
      )}

      {valueFields && valueFields.length > 0 && (
        <AvroSchemaSection fields={valueFields} raw={d.valueSchema ?? ""} />
      )}
    </div>
  )
}
