import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  ArrowLeft,
  Bell,
  Check,
  CircleQuestionMark,
  Inbox,
  Search,
} from "lucide-react"
import { IncidentPage } from "@/components/layout/PagerDutyWebview"
import { extractIncident } from "@/lib/pagerduty"
import { fetchIncident } from "@/lib/api"
import { useIncidents } from "@/hooks/useIncidents"
import { cn } from "@/lib/utils"
import type { IncidentStatus, IncidentSummary } from "@/lib/api"

// Hidden presenter page at #/pagerduty (optionally #/pagerduty/<incident-id>).
// Renders each incident from the queue as a full-screen PagerDuty-style alert
// screen so the demo can open on "the page just went off" before switching to
// the agent dashboard. Not linked from the UI - navigate by URL.
//
// Presenter controls: ←/→ cycle incidents, 1-9 jump, Esc back to dashboard.

function idFromHash(): string | null {
  const m = window.location.hash.match(/^#\/pagerduty\/([^/?#]+)/)
  return m ? decodeURIComponent(m[1]) : null
}

// ---------------------------------------------------------------------------
// PagerDuty-style app chrome (visual only)
// ---------------------------------------------------------------------------

function PagerDutyNav() {
  const items = [
    "Incidents",
    "Services",
    "People",
    "Automation",
    "Analytics",
    "Integrations",
  ]
  return (
    <nav className="flex h-12 shrink-0 items-center gap-1 bg-[#232c39] px-4">
      <div className="mr-5 flex items-center gap-2">
        <span className="inline-flex size-6 items-center justify-center rounded bg-[#06ac38]">
          <Bell className="size-3.5 text-white" />
        </span>
        <span className="text-sm font-semibold tracking-tight text-white">
          PagerDuty
        </span>
      </div>
      {items.map((label) => {
        const active = label === "Incidents"
        return (
          <button
            key={label}
            type="button"
            onClick={(e) => e.preventDefault()}
            className={cn(
              "relative h-12 px-3 text-sm transition-colors",
              active
                ? "font-medium text-white after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:bg-[#06ac38]"
                : "text-gray-400 hover:text-gray-200",
            )}
          >
            {label}
          </button>
        )
      })}
      <div className="ml-auto flex items-center gap-3">
        <div className="flex h-8 w-56 items-center gap-2 rounded bg-white/10 px-2.5 text-sm text-gray-400">
          <Search className="size-3.5" />
          Search
        </div>
        <CircleQuestionMark className="size-4 text-gray-400" />
        <span className="inline-flex size-7 items-center justify-center rounded-full bg-[#06ac38] text-xs font-semibold text-white">
          J
        </span>
      </div>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Presenter strip - incident switcher + back affordance, kept visually quiet
// ---------------------------------------------------------------------------

function StatusGlyph({ status }: { status: IncidentStatus }) {
  if (status === "completed") return <Check className="size-3.5 shrink-0 text-green-600" />
  return <AlertTriangle className="size-3.5 shrink-0 text-orange-500" />
}

function PresenterStrip({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: IncidentSummary[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="flex h-11 shrink-0 items-center gap-2 border-b border-gray-200 bg-gray-50 px-3">
      <button
        type="button"
        onClick={() => {
          window.location.hash = "#/"
        }}
        className="inline-flex items-center justify-center rounded p-1.5 text-gray-400 transition-colors hover:bg-gray-200 hover:text-gray-700"
        aria-label="Back to dashboard (Esc)"
        title="Back to dashboard (Esc)"
      >
        <ArrowLeft className="size-4" />
      </button>
      <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto">
        {incidents.map((inc, i) => {
          const active = inc.id === selectedId
          return (
            <button
              key={inc.id}
              type="button"
              onClick={() => onSelect(inc.id)}
              className={cn(
                "flex max-w-[340px] shrink-0 items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition-colors",
                active
                  ? "border-gray-300 bg-white text-gray-900 shadow-sm"
                  : "border-transparent text-gray-500 hover:bg-gray-200 hover:text-gray-800",
              )}
            >
              <span className="font-mono text-[10px] text-gray-400">{i + 1}</span>
              <StatusGlyph status={inc.status} />
              {inc.severity && (
                <span className="rounded bg-red-50 px-1 py-px text-[10px] font-semibold uppercase text-red-700">
                  {inc.severity}
                </span>
              )}
              <span className="truncate">{inc.title ?? "(untitled incident)"}</span>
            </button>
          )
        })}
      </div>
      <span className="shrink-0 text-[10px] text-gray-400">
        ← → switch · Esc dashboard
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PagerDutyPage() {
  const { incidents } = useIncidents()
  const [selectedId, setSelectedId] = useState<string | null>(() => idFromHash())

  // Payload cache so arrow-key switching mid-demo is instant. Every incident
  // in the queue is prefetched as soon as the list arrives.
  const [payloads, setPayloads] = useState<Record<string, unknown>>({})
  const requested = useRef<Set<string>>(new Set())
  useEffect(() => {
    for (const inc of incidents) {
      if (requested.current.has(inc.id)) continue
      requested.current.add(inc.id)
      fetchIncident(inc.id)
        .then((detail) => {
          setPayloads((prev) => ({ ...prev, [inc.id]: detail.payload }))
        })
        .catch(() => {
          // Allow a retry on the next poll tick.
          requested.current.delete(inc.id)
        })
    }
  }, [incidents])

  // Keep the hash as the source of truth so a refresh (or a prepared deep
  // link like #/pagerduty/PI7K3FQ) lands on the same incident.
  useEffect(() => {
    const onHashChange = () => setSelectedId(idFromHash())
    window.addEventListener("hashchange", onHashChange)
    return () => window.removeEventListener("hashchange", onHashChange)
  }, [])

  const select = useCallback((id: string) => {
    setSelectedId(id)
    window.location.hash = `#/pagerduty/${encodeURIComponent(id)}`
  }, [])

  // Fall back to the first incident in the queue when nothing is selected
  // yet (or the selected one disappeared) - derived, not synced via effect.
  const effectiveId =
    selectedId && incidents.some((inc) => inc.id === selectedId)
      ? selectedId
      : (incidents[0]?.id ?? null)

  // Presenter keyboard: ←/→ cycle, 1-9 jump, Esc back to the dashboard.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      ) {
        return
      }
      if (e.key === "Escape") {
        window.location.hash = "#/"
        return
      }
      if (incidents.length === 0) return
      const index = incidents.findIndex((inc) => inc.id === effectiveId)
      if (e.key === "ArrowRight") {
        e.preventDefault()
        select(incidents[(index + 1 + incidents.length) % incidents.length].id)
      } else if (e.key === "ArrowLeft") {
        e.preventDefault()
        select(incidents[(index - 1 + incidents.length) % incidents.length].id)
      } else if (/^[1-9]$/.test(e.key)) {
        const target = incidents[Number(e.key) - 1]
        if (target) select(target.id)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [incidents, effectiveId, select])

  // Tick once a minute so the duration counter stays fresh on screen.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  const inc = useMemo(
    () => (effectiveId ? extractIncident(payloads[effectiveId]) : null),
    [payloads, effectiveId],
  )
  const loading =
    effectiveId !== null && payloads[effectiveId] === undefined

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white text-gray-900">
      <PagerDutyNav />
      <PresenterStrip
        incidents={incidents}
        selectedId={effectiveId}
        onSelect={select}
      />
      <div className="flex-1 overflow-y-auto">
        {incidents.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-gray-400">
            <Inbox className="size-8" />
            <p className="text-sm">No incidents in the queue yet.</p>
          </div>
        ) : loading ? (
          <div className="p-10 text-center text-sm text-gray-400">
            Loading incident…
          </div>
        ) : !inc ? (
          <div className="p-10 text-center text-sm text-gray-400">
            No incident payload available to display.
          </div>
        ) : (
          <IncidentPage inc={inc} now={now} />
        )}
      </div>
    </div>
  )
}
