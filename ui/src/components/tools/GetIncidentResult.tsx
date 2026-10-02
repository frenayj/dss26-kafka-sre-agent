import { AlertTriangle } from "lucide-react"
import { Callout } from "@/components/shared/callout"
import { StatGrid, StatTile } from "@/components/shared/stat"
import { StatusBadge } from "@/components/shared/status-badge"
import { safeParseJson } from "@/lib/format"
import { severityToTone } from "./kafka/parse"
import { JsonView } from "./JsonView"

interface GetIncidentResultProps {
  content: string
}

interface IncidentBody {
  id?: string
  title?: string
  summary?: string
  description?: string
  incident_key?: string
  created_at?: string
  status?: string
  priority?: { name?: string; summary?: string }
  service?: { name?: string; summary?: string }
  // Triage may dump a flatter shape; tolerate both.
  severity?: string
  cluster?: string
  consumer_group?: string
}

function pickIncident(content: string): IncidentBody | null {
  const obj = safeParseJson(content)
  if (!obj) return null
  // PagerDuty stub wraps the incident under {"incident": {...}}.
  if (obj.incident && typeof obj.incident === "object") {
    return obj.incident as IncidentBody
  }
  return obj as IncidentBody
}

export function GetIncidentResult({ content }: GetIncidentResultProps) {
  const inc = pickIncident(content)
  if (!inc) return <JsonView content={content} />

  const severity = inc.severity ?? inc.priority?.name ?? inc.priority?.summary ?? null
  const service = inc.service?.name ?? inc.service?.summary ?? null

  const fields: Array<{ label: string; value?: string | null }> = [
    { label: "Service", value: service },
    { label: "Cluster", value: inc.cluster },
    { label: "Incident key", value: inc.incident_key },
    { label: "Created", value: inc.created_at },
  ]

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        {severity && (
          <StatusBadge tone={severityToTone(severity)}>{severity}</StatusBadge>
        )}
        {inc.id && <span className="font-mono text-xs text-muted-foreground">{inc.id}</span>}
        {inc.status && <span className="text-xs text-muted-foreground">· {inc.status}</span>}
      </div>
      {(inc.title || inc.summary) && (
        <Callout
          variant="warning"
          size="sm"
          icon={<AlertTriangle className="size-3.5" />}
          title={inc.title || inc.summary}
        />
      )}
      {inc.description && (
        <div className="text-sm text-muted-foreground whitespace-pre-wrap break-words">
          {inc.description}
        </div>
      )}
      <StatGrid cols={2}>
        {fields
          .filter((f) => f.value)
          .map(({ label, value }) => (
            <StatTile key={label} label={label} value={value} />
          ))}
      </StatGrid>
    </div>
  )
}
