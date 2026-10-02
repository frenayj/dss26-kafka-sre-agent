import { AlertTriangle, Check, Inbox, X } from "lucide-react"
import { CountPill } from "@/components/shared/count-pill"
import { EmptyState } from "@/components/shared/empty-state"
import { StatusBadge } from "@/components/shared/status-badge"
import { severityToTone } from "@/components/tools/kafka/parse"
import { Spinner } from "@/components/ui/spinner"
import { relativeTime } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { IncidentStatus, IncidentSummary } from "@/lib/api"
import { SidebarSection } from "./SidebarSection"

interface IncidentsListProps {
  incidents: IncidentSummary[]
  selectedId: string | null
  onSelect: (id: string) => void
  disabled?: boolean
  open: boolean
  onToggle: () => void
}

function StatusIcon({ status }: { status: IncidentStatus }) {
  switch (status) {
    case "in_progress":
      return <Spinner className="size-3 shrink-0 text-info" />
    case "completed":
      return <Check className="size-3 shrink-0 text-success" />
    case "pending":
      return <AlertTriangle className="size-3 shrink-0 text-warning" />
    default:
      return <X className="size-3 shrink-0 text-destructive" />
  }
}

/** Severity pill + title + status icon row shared by cards and summary. */
function IncidentHeadline({ incident }: { incident: IncidentSummary }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <StatusIcon status={incident.status} />
      {incident.severity && (
        <StatusBadge tone={severityToTone(incident.severity)}>
          {incident.severity}
        </StatusBadge>
      )}
      <span className="min-w-0 flex-1 truncate text-xs font-medium">
        {incident.title ?? "(no title)"}
      </span>
    </div>
  )
}

/**
 * Per-incident card: severity badge + title + service + age + status.
 * Click selects (the parent Run button runs on the current selection).
 * Trash icon on hover deletes the incident from the queue.
 */
export function IncidentsList({
  incidents,
  selectedId,
  onSelect,
  disabled = false,
  open,
  onToggle,
}: IncidentsListProps) {
  const selected = incidents.find((inc) => inc.id === selectedId)

  return (
    <div>
      <SidebarSection
        label="Incidents"
        icon={<Inbox className="size-3.5 shrink-0" />}
        meta={<CountPill>{incidents.length}</CountPill>}
        open={open}
        onOpenChange={() => onToggle()}
      >
        {incidents.length === 0 ? (
          <EmptyState
            icon={<Inbox />}
            title="No incidents"
            description="No incidents in the queue yet."
          />
        ) : (
          <ul className="space-y-1.5">
            {incidents.map((inc) => {
              const isSelected = inc.id === selectedId
              return (
                <li key={inc.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(inc.id)}
                    disabled={disabled}
                    className={cn(
                      "w-full space-y-1.5 rounded border p-2 text-left transition-colors",
                      isSelected
                        ? "border-ring bg-accent"
                        : "border-border/50 bg-card/40 hover:border-border hover:bg-accent/50",
                      disabled && "pointer-events-none opacity-60",
                    )}
                  >
                    <IncidentHeadline incident={inc} />
                    <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
                      {inc.service && (
                        <span className="truncate">{inc.service}</span>
                      )}
                      <span className="ml-auto">
                        {relativeTime(inc.created_at)}
                      </span>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </SidebarSection>

      {!open && selected && (
        <div className="px-2 pb-1">
          <div className="space-y-1 rounded border border-ring/60 bg-card/60 p-2">
            <IncidentHeadline incident={selected} />
            {selected.service && (
              <div className="truncate font-mono text-[10px] text-muted-foreground">
                {selected.service}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
