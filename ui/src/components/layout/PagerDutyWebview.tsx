import { useEffect, useState } from "react"
import {
  AlertTriangle,
  Bell,
  Check,
  ChevronDown,
  ExternalLink,
  Pencil,
  X,
} from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { extractIncident } from "@/lib/pagerduty"
import type { PagerDutyIncident } from "@/lib/pagerduty"

interface PagerDutyWebviewProps {
  open: boolean
  onClose: () => void
  /** The raw incident payload (the `incident` key inside an incidents-store
   *  row's `payload`). Shape mirrors PagerDuty's REST incident object. */
  payload: unknown
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatDateLong(iso: string | null): string {
  if (!iso) return "-"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  })
}

function formatRelativeDays(iso: string | null): string {
  if (!iso) return ""
  const ms = Date.now() - new Date(iso).getTime()
  if (Number.isNaN(ms)) return ""
  const days = Math.floor(ms / 86_400_000)
  if (days <= 0) {
    const hours = Math.floor(ms / 3_600_000)
    if (hours <= 0) return "(just now)"
    return `(${hours} hour${hours === 1 ? "" : "s"} ago)`
  }
  return `(${days} day${days === 1 ? "" : "s"} ago)`
}

function formatDuration(iso: string | null, nowMs: number): string {
  if (!iso) return "-"
  const start = new Date(iso).getTime()
  if (Number.isNaN(start)) return "-"
  const total = Math.max(0, nowMs - start)
  const days = Math.floor(total / 86_400_000)
  const hours = Math.floor((total % 86_400_000) / 3_600_000)
  const mins = Math.floor((total % 3_600_000) / 60_000)
  return `${days}d ${String(hours).padStart(2, "0")}h ${String(mins).padStart(2, "0")}m`
}

function formatStatusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase()
}

function formatUrgencyLabel(urgency: string): string {
  if (!urgency || urgency === "-") return urgency
  return urgency.charAt(0).toUpperCase() + urgency.slice(1).toLowerCase()
}

function statusColor(status: string): string {
  const s = status.toLowerCase()
  if (s === "triggered") return "text-orange-600"
  if (s === "acknowledged") return "text-yellow-600"
  if (s === "resolved") return "text-green-600"
  return "text-gray-700"
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PagerDutyWebview({ open, onClose, payload }: PagerDutyWebviewProps) {
  const inc = extractIncident(payload)

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        className="!max-w-[min(1100px,calc(100vw-2rem))] w-full h-[calc(100vh-4rem)] !top-[2rem] !translate-y-0 p-0 bg-white border-gray-300 overflow-hidden flex flex-col"
        showCloseButton={false}
      >
        <DialogTitle className="sr-only">PagerDuty incident webview</DialogTitle>
        <DialogDescription className="sr-only">
          A read-only PagerDuty-style view of the incident payload
        </DialogDescription>

        {/* Top chrome bar - mimics a browser/app chrome */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 bg-gray-50 shrink-0">
          <Bell className="size-4 text-green-600 shrink-0" />
          <div className="text-xs font-medium text-gray-600">PagerDuty</div>
          <div className="ml-2 text-xs text-gray-500 font-mono truncate">
            {inc?.htmlUrl ?? "-"}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto inline-flex items-center justify-center rounded p-1 text-gray-500 hover:bg-gray-200 hover:text-gray-900 transition-colors"
            title="Close (Esc)"
          >
            <X className="size-4" />
            <span className="sr-only">Close</span>
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto bg-white text-gray-900">
          {!inc ? (
            <div className="p-10 text-sm text-gray-500 text-center">
              No incident payload available to display.
            </div>
          ) : (
            <LiveIncidentPage inc={inc} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** IncidentPage with a clock that ticks once a minute so the duration counter
 *  stays fresh. DialogContent only mounts while the dialog is open, so the
 *  clock starts from "now" on every open and stops when it closes. */
function LiveIncidentPage({ inc }: { inc: PagerDutyIncident }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])
  return <IncidentPage inc={inc} now={now} />
}

// ---------------------------------------------------------------------------
// Subviews - each maps to a region of the screenshot
// ---------------------------------------------------------------------------

export function IncidentPage({ inc, now }: { inc: PagerDutyIncident; now: number }) {
  return (
    <div className="px-8 py-6 max-w-[1100px] mx-auto">
      {/* Breadcrumb */}
      <div className="text-xs text-blue-700 mb-2">
        <a className="hover:underline" href="#" onClick={(e) => e.preventDefault()}>
          Incidents
        </a>
        <span className="mx-1 text-gray-400">›</span>
        <span className="text-gray-700">Incident #{inc.number ?? "-"}</span>
      </div>

      {/* Title strip */}
      <HeaderStrip inc={inc} now={now} />

      {/* Action bar */}
      <ActionBar />

      {/* Details grid */}
      <DetailsGrid inc={inc} />

      {/* Custom fields */}
      <CustomFieldsSection />

      {/* Tabs + alerts table */}
      <AlertsSection inc={inc} />
    </div>
  )
}

function HeaderStrip({ inc, now }: { inc: PagerDutyIncident; now: number }) {
  const showAnomaly = true // PD shows this badge when the incident has no recent neighbors

  return (
    <div className="flex items-start gap-6 py-4">
      <div className="flex-1 min-w-0">
        <div className="inline-flex items-center gap-1 rounded bg-blue-50 border border-blue-200 px-2 py-0.5 text-xs text-blue-700 mb-2">
          Base Incident
          <ChevronDown className="size-3" />
        </div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-gray-900 truncate">
            {inc.title}
          </h1>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-blue-700 hover:underline shrink-0"
            onClick={(e) => e.preventDefault()}
          >
            <Pencil className="size-3" />
            Edit
          </button>
        </div>
        {showAnomaly && (
          <div className="mt-3 flex items-start gap-3">
            <span className="inline-flex items-center rounded-full bg-orange-100 text-orange-800 border border-orange-200 px-2.5 py-0.5 text-xs font-medium uppercase tracking-wide">
              Anomaly
            </span>
            <span className="text-sm text-gray-600">
              Not similar to any incidents on this service in the preceding 30 days.
            </span>
          </div>
        )}
      </div>

      <MetaCell label="Priority">
        <div className="inline-flex items-center gap-1 border border-gray-300 rounded px-2 py-1 text-sm">
          <span className="font-semibold">{inc.priority ?? "-"}</span>
          <ChevronDown className="size-3 text-gray-500" />
        </div>
      </MetaCell>
      <MetaCell label="Status">
        <div className={`text-base font-semibold ${statusColor(inc.status)}`}>
          {formatStatusLabel(inc.status)}
        </div>
      </MetaCell>
      <MetaCell label="Duration">
        <div className="text-base font-semibold text-gray-900 tabular-nums">
          {formatDuration(inc.createdAt, now)}
        </div>
      </MetaCell>
    </div>
  )
}

function MetaCell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-1 shrink-0 border-l border-gray-200 pl-6 min-w-[120px]">
      <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">
        {label}
      </span>
      {children}
    </div>
  )
}

function ActionBar() {
  // These buttons are visual-only - no backend action. The "Resolve" button
  // is the green call-to-action on the right; the others are secondary.
  const actions = [
    "Acknowledge",
    "Escalate",
    "Reassign",
    "Add Responders",
    "Run Workflow",
    "Send Status Update",
    "More",
  ]
  return (
    <div className="flex items-center gap-2 flex-wrap py-3 border-y border-gray-200">
      {actions.map((label) => (
        <button
          key={label}
          type="button"
          className="inline-flex items-center gap-1 border border-gray-300 bg-white hover:bg-gray-50 text-sm text-gray-800 rounded px-3 py-1.5"
          onClick={(e) => e.preventDefault()}
        >
          {label}
          {(label === "Escalate" || label === "Run Workflow" || label === "Send Status Update" || label === "More") && (
            <ChevronDown className="size-3 text-gray-500" />
          )}
        </button>
      ))}
      <button
        type="button"
        className="ml-auto inline-flex items-center gap-1.5 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded px-4 py-1.5"
        onClick={(e) => e.preventDefault()}
      >
        <Check className="size-4" />
        Resolve
      </button>
    </div>
  )
}

function DetailsGrid({ inc }: { inc: PagerDutyIncident }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-3 py-6">
      <div className="space-y-3">
        <DetailRow label="Status">
          <span className={`font-semibold ${statusColor(inc.status)}`}>
            {formatStatusLabel(inc.status)}
          </span>
        </DetailRow>
        <DetailRow label="Opened">
          <span className="text-sm text-gray-900">
            {formatDateLong(inc.createdAt)}
          </span>
          <span className="text-sm text-gray-500 ml-1">
            {formatRelativeDays(inc.createdAt)}
          </span>
        </DetailRow>
        <DetailRow label="Assigned to">
          {inc.assignees.length === 0 ? (
            <span className="text-gray-500">-</span>
          ) : (
            inc.assignees.map((name) => (
              <a
                key={name}
                href="#"
                onClick={(e) => e.preventDefault()}
                className="text-sm text-blue-700 hover:underline mr-2"
              >
                {name}
              </a>
            ))
          )}
        </DetailRow>
        <DetailRow label="Escalation Policy">
          <a
            href="#"
            onClick={(e) => e.preventDefault()}
            className="text-sm text-blue-700 hover:underline"
          >
            {inc.escalationPolicy ?? "-"}
          </a>
        </DetailRow>
        <DetailRow label="Responders">
          <span className="text-sm text-gray-900">{inc.assignees.length}</span>
          <span
            className="ml-1.5 inline-flex items-center justify-center size-3.5 rounded-full bg-gray-100 text-gray-500 text-[9px] cursor-help"
            title="Number of people responding to this incident"
          >
            i
          </span>
        </DetailRow>
      </div>

      <div className="space-y-3">
        <DetailRow label="Urgency">
          <div className="inline-flex items-center gap-1 border border-gray-300 rounded px-2 py-0.5 text-sm">
            {formatUrgencyLabel(inc.urgency)}
            <ChevronDown className="size-3 text-gray-500" />
          </div>
        </DetailRow>
        <DetailRow label="Main service">
          <a
            href={inc.serviceUrl ?? "#"}
            onClick={(e) => !inc.serviceUrl && e.preventDefault()}
            target={inc.serviceUrl ? "_blank" : undefined}
            rel="noreferrer"
            className="text-sm text-blue-700 hover:underline inline-flex items-center gap-1"
          >
            {inc.service ?? "-"}
            <Pencil className="size-3 text-gray-400" />
          </a>
        </DetailRow>
        <DetailRow label="Impacted service">
          <a
            href={inc.serviceUrl ?? "#"}
            onClick={(e) => !inc.serviceUrl && e.preventDefault()}
            target={inc.serviceUrl ? "_blank" : undefined}
            rel="noreferrer"
            className="text-sm text-blue-700 hover:underline"
          >
            {inc.service ?? "-"}
          </a>
        </DetailRow>
        <DetailRow label="Service description">
          <div className="text-sm text-gray-700 space-y-2">
            {inc.description ? (
              <p>{inc.description}</p>
            ) : (
              <>
                <p>
                  Your first service - describe what this service is monitoring and any
                  information that will help responders.
                </p>
                <p>
                  For example: What is the SLA of this service? Where are the
                  runbooks for this service stored? What tier level is this service?
                </p>
              </>
            )}
          </div>
        </DetailRow>
      </div>
    </div>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 items-start">
      <div className="text-[11px] uppercase tracking-wider text-gray-500 font-medium pt-0.5">
        {label}
      </div>
      <div className="text-sm text-gray-900">{children}</div>
    </div>
  )
}

function CustomFieldsSection() {
  return (
    <div className="py-5 border-t border-gray-200">
      <h3 className="text-base font-semibold text-gray-900 mb-2">Custom Fields</h3>
      <p className="text-sm text-gray-600">
        No custom fields configured for incidents.{" "}
        <a
          href="#"
          onClick={(e) => e.preventDefault()}
          className="text-blue-700 hover:underline"
        >
          Configure custom fields
        </a>{" "}
        to display them on this and other incidents.
      </p>
    </div>
  )
}

function AlertsSection({ inc }: { inc: PagerDutyIncident }) {
  const tabs = [
    "Alerts",
    "Status Updates",
    "Timeline",
    "Automation Actions Log",
    "Past Incidents",
    "Related Incidents",
  ]
  const [active, setActive] = useState("Alerts")

  return (
    <div className="border-t border-gray-200 pt-2">
      <div className="flex items-center gap-6 border-b border-gray-200">
        {tabs.map((label) => {
          const isActive = label === active
          const showZeroCount = label === "Related Incidents"
          return (
            <button
              key={label}
              type="button"
              onClick={() => setActive(label)}
              className={
                "py-3 text-sm transition-colors border-b-2 -mb-px " +
                (isActive
                  ? "text-blue-700 font-medium border-blue-700"
                  : "text-gray-700 hover:text-gray-900 border-transparent")
              }
            >
              {label}
              {showZeroCount && (
                <span className="ml-1.5 inline-flex items-center justify-center min-w-[20px] px-1.5 rounded-full bg-gray-200 text-gray-600 text-xs">
                  0
                </span>
              )}
            </button>
          )
        })}
      </div>

      {active === "Alerts" ? (
        <AlertsTable inc={inc} />
      ) : (
        <div className="py-12 text-center text-sm text-gray-500">
          {active} - not implemented in this view.
        </div>
      )}
    </div>
  )
}

function AlertsTable({ inc }: { inc: PagerDutyIncident }) {
  return (
    <div className="py-4">
      <div className="flex items-center gap-3 pb-3">
        <span className="text-sm text-gray-700">
          {inc.alertCount} Alert{inc.alertCount === 1 ? "" : "s"}{" "}
          <span className="text-gray-500">({inc.triggeredCount} Triggered)</span>
        </span>
        <span className="inline-flex items-center gap-1 rounded bg-gray-100 text-gray-700 px-2 py-0.5 text-xs">
          Grouping off
          <span
            className="inline-flex items-center justify-center size-3.5 rounded-full bg-gray-300 text-gray-600 text-[9px]"
            title="Alert grouping is disabled for this incident"
          >
            i
          </span>
        </span>
      </div>

      <table className="w-full border border-gray-200 rounded text-sm">
        <thead>
          <tr className="bg-gray-50 text-left text-xs uppercase tracking-wider text-gray-600">
            <th className="px-3 py-2 w-8">
              <input type="checkbox" disabled className="cursor-not-allowed" />
            </th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Severity</th>
            <th className="px-3 py-2">Summary</th>
            <th className="px-3 py-2">Created ↓</th>
            <th className="px-3 py-2">Service</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-gray-200 hover:bg-gray-50">
            <td className="px-3 py-3">
              <input type="checkbox" />
            </td>
            <td className="px-3 py-3">
              <span className="inline-flex items-center gap-1 rounded-full bg-orange-50 text-orange-700 border border-orange-200 px-2 py-0.5 text-xs">
                <AlertTriangle className="size-3" />
                {formatStatusLabel(inc.status)}
              </span>
            </td>
            <td className="px-3 py-3 text-gray-700">
              {inc.urgency.toLowerCase() === "high" ? "Critical" : "Info"}
            </td>
            <td className="px-3 py-3">
              {inc.htmlUrl ? (
                <a
                  href={inc.htmlUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-700 hover:underline inline-flex items-center gap-1"
                >
                  {inc.alertSummary}
                  <ExternalLink className="size-3" />
                </a>
              ) : (
                <span>{inc.alertSummary}</span>
              )}
            </td>
            <td className="px-3 py-3 text-gray-700 tabular-nums">
              {formatDateLong(inc.createdAt)}
            </td>
            <td className="px-3 py-3">
              <a
                href={inc.serviceUrl ?? "#"}
                onClick={(e) => !inc.serviceUrl && e.preventDefault()}
                target={inc.serviceUrl ? "_blank" : undefined}
                rel="noreferrer"
                className="text-blue-700 hover:underline"
              >
                {inc.service ?? "-"}
              </a>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}
