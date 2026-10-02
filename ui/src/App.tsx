import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { usePanelRef } from "react-resizable-panels"
import { toast } from "sonner"
import { Sidebar } from "@/components/layout/Sidebar"
import { ChatArea } from "@/components/layout/ChatArea"
import { LensesAuthDialog } from "@/components/layout/LensesAuthDialog"
import { RunSummaryDialog } from "@/components/layout/RunSummaryDialog"
import { HandoffsDialog } from "@/components/handoffs/HandoffsDialog"
import { RightPanel } from "@/components/layout/RightPanel"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { FocusRequest } from "@/components/chat/EventStream"
import { useIncidents } from "@/hooks/useIncidents"
import { useMcpServers } from "@/hooks/useMcpServers"
import { useModels } from "@/hooks/useModels"
import { usePanelOpen } from "@/hooks/usePanelOpen"
import { usePing } from "@/hooks/usePing"
import { usePresets } from "@/hooks/usePresets"
import { useRunHistory } from "@/hooks/useRunHistory"
import { useRunStream } from "@/hooks/useRunStream"
import { useSkills } from "@/hooks/useSkills"
import { buildAgentCalls } from "@/lib/handoffs"
import { claimIncident, type RunSummary } from "@/lib/api"

const DEFAULT_PRESET = "full"

function toggled(set: Set<string>, name: string, present: boolean): Set<string> {
  const next = new Set(set)
  if (present) next.add(name)
  else next.delete(name)
  return next
}

export default function App() {
  const { presets } = usePresets()
  const { ok: agentOk, error: agentError, ping } = usePing()
  const { state, start, follow, replay, cancel, reset } = useRunStream()
  const { runs, refetch: refetchRuns, deleteRun, renameRun } = useRunHistory()
  const { skills } = useSkills()
  const { servers: mcpServers } = useMcpServers()
  const { incidents, refetch: refetchIncidents } = useIncidents()

  // One setting on the server, shared with the operator console: runs use
  // it without the dashboard passing it along.
  const { models, select: selectModel } = useModels()

  // Runs use the "full" preset, or the first one the server offers.
  const preset = presets[DEFAULT_PRESET] ? DEFAULT_PRESET : (Object.keys(presets)[0] ?? "")

  // Every skill and MCP server starts enabled; the sidebar toggles record the
  // ones switched off, and the enabled sets are derived from that.
  const [disabledSkills, setDisabledSkills] = useState<Set<string>>(() => new Set())
  const [disabledServers, setDisabledServers] = useState<Set<string>>(() => new Set())
  const enabledSkills = useMemo(
    () => new Set(skills.map((s) => s.name).filter((n) => !disabledSkills.has(n))),
    [skills, disabledSkills],
  )
  const enabledServers = useMemo(
    () => new Set(mcpServers.map((s) => s.name).filter((n) => !disabledServers.has(n))),
    [mcpServers, disabledServers],
  )

  // Select the most recent incident once the list first arrives, and fall
  // back to it if the selected incident disappears. Adjusted during render
  // (rather than in an effect) so no frame renders a stale selection.
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null)
  const [incidentsSeeded, setIncidentsSeeded] = useState(false)
  if (!incidentsSeeded && incidents.length > 0) {
    setIncidentsSeeded(true)
    setSelectedIncidentId(incidents[0].id)
  } else if (selectedIncidentId && !incidents.some((i) => i.id === selectedIncidentId)) {
    setSelectedIncidentId(incidents[0]?.id ?? null)
  }

  // End-of-run summary dialog (on-call team vs agent, time and cost). Opens once
  // per completed live run; ``summaryShownRef`` guards against re-opening on
  // every render while ``status`` stays "done".
  const [summaryOpen, setSummaryOpen] = useState<boolean>(false)
  const [handoffsOpen, setHandoffsOpen] = useState<boolean>(false)
  const summaryShownRef = useRef<string | null>(null)

  // Per-side collapse state, persisted to localStorage. Open by default.
  // Left drives the controlled SidebarProvider; right drives the collapsible
  // ResizablePanel through its imperative handle.
  const left = usePanelOpen("left", true)
  const right = usePanelOpen("right", true)
  const rightPanelRef = usePanelRef()

  const toggleRight = useCallback(() => {
    const handle = rightPanelRef.current
    if (!handle) return
    if (handle.isCollapsed()) {
      handle.expand()
      right.setOpen(true)
    } else {
      handle.collapse()
      right.setOpen(false)
    }
  }, [rightPanelRef, right])

  // Apply the persisted collapsed state once on mount.
  const rightInitiallyOpenRef = useRef(right.open)
  useEffect(() => {
    if (!rightInitiallyOpenRef.current) rightPanelRef.current?.collapse()
  }, [rightPanelRef])

  // Cross-pane "focus this tool" coordination. The Timeline (right panel)
  // fires a request; EventStream (chat pane) opens the ancestor chain,
  // scrolls the matching card into view, and flashes it.
  // ``bump`` makes re-clicking the same row re-fire the action.
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null)
  const requestFocusTool = useCallback((toolCallId: string) => {
    setFocusRequest((prev) => ({ id: toolCallId, bump: (prev?.bump ?? 0) + 1 }))
  }, [])

  // Keyboard shortcuts: `[` toggles the left sidebar, `]` toggles the right
  // panel. Skipped when the user is typing into an input / textarea /
  // contenteditable so we don't hijack regular bracket presses.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const target = e.target as HTMLElement | null
      if (target) {
        const tag = target.tagName
        if (
          tag === "INPUT" ||
          tag === "TEXTAREA" ||
          tag === "SELECT" ||
          target.isContentEditable
        ) {
          return
        }
      }
      if (e.key === "[") {
        e.preventDefault()
        left.toggle()
      } else if (e.key === "]") {
        e.preventDefault()
        toggleRight()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [left, toggleRight])

  // Refetch history + incidents whenever a live or followed run finishes so
  // the history list and the incident's status indicator update immediately.
  useEffect(() => {
    if (state.mode !== "live" && !state.following) return
    if (state.status === "done" || state.status === "error") {
      refetchRuns()
      refetchIncidents()
    }
  }, [state.mode, state.following, state.status, refetchRuns, refetchIncidents])

  // Surface live-run failures as a toast (the stream also renders the error
  // inline; the toast catches eyes that are on the sidebar or right panel).
  const errorToastRef = useRef<string | null>(null)
  useEffect(() => {
    if (state.mode !== "live" || state.status !== "error") return
    // A run stopped on purpose is not a failure.
    if (state.error?.type === "Cancelled") return
    const key = state.runId ?? (state.startedAt ? String(state.startedAt) : "unknown")
    if (errorToastRef.current === key) return
    errorToastRef.current = key
    toast.error("Run failed", {
      description: "The agent stream ended with an error - see the feed for details.",
    })
  }, [state.mode, state.status, state.error, state.runId, state.startedAt])

  // Pop the run summary once a live run completes. Keyed
  // on the run id (falling back to startedAt) so it fires exactly once per
  // run, not on every re-render while status stays "done". Replays don't
  // trigger it - only fresh live runs.
  useEffect(() => {
    if (state.mode !== "live" || state.status !== "done") return
    const key = state.runId ?? (state.startedAt ? String(state.startedAt) : null)
    if (key && summaryShownRef.current !== key) {
      summaryShownRef.current = key
      setSummaryOpen(true)
    }
  }, [state.mode, state.status, state.runId, state.startedAt])

  // What passed between the agents, per call - for the agent cards, the
  // right panel's context chart and the handoff view.
  const agentCalls = useMemo(
    () => buildAgentCalls(state.events, state.toolCalls, state.status !== "running"),
    [state.events, state.toolCalls, state.status],
  )
  const runStart = agentCalls[0]?.startedAt ?? 0
  const runEnd = state.events[state.events.length - 1]?.at ?? runStart

  const handleRun = useCallback(() => {
    if (!selectedIncidentId) return
    start(
      preset,
      selectedIncidentId,
      Array.from(enabledSkills),
      Array.from(enabledServers),
    )
  }, [start, preset, selectedIncidentId, enabledSkills, enabledServers])

  // Live PagerDuty: a fresh page arrives flagged ``auto_run``. Claim it (only
  // one open dashboard wins) and start the run without a click - the agent's
  // first act is to acknowledge the page in PagerDuty.
  const autoRunTriedRef = useRef<Set<string>>(new Set())
  const claimingRef = useRef(false)
  useEffect(() => {
    // Following a run from history doesn't block a claim - only a live run does.
    if ((state.mode === "live" && state.status === "running") || claimingRef.current) return
    // Wait for the skill + server lists, or a page that is already waiting
    // when the dashboard opens would run with no skills and no MCP servers.
    if (!preset || enabledServers.size === 0 || enabledSkills.size === 0) return
    const next = incidents.find(
      (i) => i.auto_run && i.status === "pending" && !autoRunTriedRef.current.has(i.id),
    )
    if (!next) return
    autoRunTriedRef.current.add(next.id)
    claimingRef.current = true
    claimIncident(next.id)
      .then((claimed) => {
        if (!claimed) return
        setSelectedIncidentId(next.id)
        toast.info("PagerDuty incident received", { description: next.title ?? next.id })
        start(
          preset,
          next.id,
          Array.from(enabledSkills),
          Array.from(enabledServers),
        )
      })
      .catch((err: unknown) => {
        toast.error("Could not start the run", {
          description: err instanceof Error ? err.message : String(err),
        })
      })
      .finally(() => {
        claimingRef.current = false
      })
  }, [incidents, state.mode, state.status, preset, enabledSkills, enabledServers, start])

  // Runs execute on the server, so one may already be in progress when this
  // page opens: after a reload, after switching back from another view, or
  // when another dashboard started it. Pick it up as the current run.
  const followedRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    if (state.status === "running") return
    const active = incidents.find((i) => i.status === "in_progress" && i.last_run_id)
    const runId = active?.last_run_id
    if (!active || !runId || followedRef.current.has(runId) || runId === state.runId) return
    followedRef.current.add(runId)
    follow(runId, preset || DEFAULT_PRESET, active.id)
  }, [incidents, state.status, state.runId, preset, follow])

  const handleToggleSkill = useCallback((name: string, value: boolean) => {
    setDisabledSkills((prev) => toggled(prev, name, !value))
  }, [])

  const handleToggleServer = useCallback((name: string, value: boolean) => {
    setDisabledServers((prev) => toggled(prev, name, !value))
  }, [])

  const handleReplay = useCallback(
    (run: RunSummary) => {
      replay(run.id, run.preset, run.incident_id)
    },
    [replay],
  )

  const handleDeleteRun = useCallback(
    (id: string) => {
      deleteRun(id).catch((err: unknown) => {
        toast.error("Failed to delete run", {
          description: err instanceof Error ? err.message : String(err),
        })
      })
      if (state.runId === id) reset()
    },
    [deleteRun, state.runId, reset],
  )

  const needsAuthUrl =
    ping?.status === "needs_auth" && typeof ping.auth_url === "string"
      ? ping.auth_url
      : null

  const agentLabel = agentOk
    ? `MCP ready (${Object.keys((ping?.tools as object) ?? {}).length} servers)`
    : ping?.status === "needs_auth"
      ? "Sign in required"
      : agentError
        ? "Agent offline"
        : "Connecting…"

  return (
    <TooltipProvider delayDuration={200}>
      <SidebarProvider
        open={left.open}
        onOpenChange={left.setOpen}
        style={{ "--sidebar-width": "260px" } as React.CSSProperties}
        className="h-screen min-h-0 overflow-hidden"
      >
        <Sidebar
          incidents={incidents}
          selectedIncidentId={selectedIncidentId}
          onSelectIncident={setSelectedIncidentId}
          onRun={handleRun}
          onStop={cancel}
          status={state.status}
          mode={state.mode}
          agentOk={agentOk}
          agentLabel={agentLabel}
          skills={skills}
          enabledSkills={enabledSkills}
          onToggleSkill={handleToggleSkill}
          mcpServers={mcpServers}
          enabledServers={enabledServers}
          onToggleServer={handleToggleServer}
          models={models}
          onModelSelect={selectModel}
          runs={runs}
          activeRunId={state.runId ?? null}
          onReplayRun={handleReplay}
          onDeleteRun={handleDeleteRun}
          onRenameRun={renameRun}
        />

        <SidebarInset className="h-screen min-h-0 min-w-0 overflow-hidden">
          <ResizablePanelGroup orientation="horizontal" className="min-h-0">
            <ResizablePanel id="activity" minSize={480} className="min-w-0">
              <ChatArea
                rows={state.rows}
                toolCalls={state.toolCalls}
                agentMetrics={state.agentMetrics}
                status={state.status}
                mode={state.mode}
                following={state.following}
                onShowSummary={() => setSummaryOpen(true)}
                agentCalls={agentCalls}
                onShowHandoffs={() => setHandoffsOpen(true)}
                focusRequest={focusRequest}
                rightPanelOpen={right.open}
                onToggleRightPanel={toggleRight}
              />
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel
              id="inspector"
              panelRef={rightPanelRef}
              defaultSize={440}
              minSize={340}
              maxSize="55"
              collapsible
              collapsedSize={0}
              onResize={(size) => {
                // Keep the persisted open flag in sync with drag-collapses.
                const isOpen = size.inPixels >= 1
                if (isOpen !== right.open) right.setOpen(isOpen)
              }}
            >
              <RightPanel
                toolCalls={state.toolCalls}
                agentCalls={agentCalls}
                runStart={runStart}
                runEnd={runEnd}
                onSelectTool={requestFocusTool}
                onClose={() => {
                  rightPanelRef.current?.collapse()
                  right.setOpen(false)
                }}
              />
            </ResizablePanel>
          </ResizablePanelGroup>
        </SidebarInset>
      </SidebarProvider>
      <LensesAuthDialog authUrl={needsAuthUrl} />
      <RunSummaryDialog
        open={summaryOpen}
        onOpenChange={setSummaryOpen}
        state={state}
        incidentId={selectedIncidentId}
      />
      <HandoffsDialog
        open={handoffsOpen}
        onOpenChange={setHandoffsOpen}
        calls={agentCalls}
        start={runStart}
        end={runEnd}
        incidentId={selectedIncidentId}
      />
    </TooltipProvider>
  )
}
