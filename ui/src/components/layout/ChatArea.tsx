import { Clock, PanelRight, Waypoints } from "lucide-react"
import { PanelToggleButton } from "@/components/shared/panel-toggle-button"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar"
import { Spinner } from "@/components/ui/spinner"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { AgentCall } from "@/lib/handoffs"
import type { AgentMetrics, Row, StreamMode, StreamStatus, ToolCall } from "@/lib/types"
import { EventStream, type FocusRequest } from "@/components/chat/EventStream"
import { LiveUsageBar } from "./LiveUsageBar"

interface ChatAreaProps {
  rows: Row[]
  toolCalls: Map<string, ToolCall>
  agentMetrics: Map<string, AgentMetrics>
  status: StreamStatus
  mode: StreamMode
  /** Replay of a run another dashboard is still executing - its new
   *  activity keeps streaming in. */
  following?: boolean
  /** Re-open the end-of-run summary dialog. Shown once a run has
   *  completed so the summary can be brought back after dismissal. */
  onShowSummary?: () => void
  /** Each agent call's handoff, for the agent cards in the feed. */
  agentCalls?: AgentCall[]
  /** Open the handoff view (what each agent was handed). */
  onShowHandoffs?: () => void
  /** Latest "scroll to + expand this tool" request, forwarded from
   *  Timeline clicks in the right panel. */
  focusRequest?: FocusRequest | null
  /** Right inspector panel state + toggle (rendered in this header). */
  rightPanelOpen?: boolean
  onToggleRightPanel?: () => void
}

export function ChatArea({
  rows,
  toolCalls,
  agentMetrics,
  status,
  mode,
  following = false,
  onShowSummary,
  agentCalls,
  onShowHandoffs,
  focusRequest = null,
  rightPanelOpen = true,
  onToggleRightPanel,
}: ChatAreaProps) {
  const replay = mode === "replay"
  const followingLive = replay && following && status === "running"
  const { open: sidebarOpen } = useSidebar()
  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
        {!sidebarOpen && (
          <Tooltip>
            <TooltipTrigger asChild>
              <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
            </TooltipTrigger>
            <TooltipContent side="bottom" className="flex items-center gap-2">
              Open sidebar
              <Kbd>[</Kbd>
            </TooltipContent>
          </Tooltip>
        )}
        <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          {status === "running" && (!replay || followingLive) && (
            <Spinner className="size-3.5" />
          )}
          {onShowHandoffs && agentCalls && agentCalls.length > 0 && (
            <Button size="xs" variant="outline" onClick={onShowHandoffs}>
              <Waypoints className="size-3.5 text-primary" /> Handoffs
            </Button>
          )}
          {status === "done" && onShowSummary && (
            <Button size="xs" variant="outline" onClick={onShowSummary}>
              <Clock className="size-3.5 text-primary" /> Summary
            </Button>
          )}
          {onToggleRightPanel && (
            <PanelToggleButton
              label={rightPanelOpen ? "Collapse right panel" : "Open right panel"}
              shortcut="]"
              onClick={onToggleRightPanel}
            >
              <PanelRight className="size-4" />
            </PanelToggleButton>
          )}
        </div>
      </header>

      <LiveUsageBar agentMetrics={agentMetrics} toolCalls={toolCalls} />

      <EventStream
        rows={rows}
        toolCalls={toolCalls}
        focusRequest={focusRequest}
        agentCalls={agentCalls}
      />
    </div>
  )
}
