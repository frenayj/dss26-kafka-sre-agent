import { useState } from "react"
import { PanelLeftClose, Play, Square } from "lucide-react"
import { LensesLogo } from "@/components/icons/lenses"
import { ModeToggle } from "@/components/mode-toggle"
import { StatusDot } from "@/components/shared/status-dot"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import {
  Sidebar as SidebarRoot,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { StreamMode, StreamStatus } from "@/lib/types"
import type {
  AgentRole,
  IncidentSummary,
  McpServerInfo,
  ModelAlias,
  ModelSelection,
  RunSummary,
  SkillInfo,
} from "@/lib/api"
import { IncidentsList } from "./IncidentsList"
import { McpServersList } from "./McpServersList"
import { ModelSettings } from "./ModelSettings"
import { RunHistoryList } from "./RunHistoryList"
import { SkillsList } from "./SkillsList"

interface SidebarProps {
  incidents: IncidentSummary[]
  selectedIncidentId: string | null
  onSelectIncident: (id: string) => void

  onRun: () => void
  onStop: () => void
  status: StreamStatus
  mode: StreamMode
  agentOk: boolean
  agentLabel: string

  // Skills
  skills: SkillInfo[]
  enabledSkills: Set<string>
  onToggleSkill: (name: string, value: boolean) => void

  // MCP servers
  mcpServers: McpServerInfo[]
  enabledServers: Set<string>
  onToggleServer: (name: string, value: boolean) => void

  // Per-role gateway model selection (claude/mistral/gpt aliases)
  /** The server's model per role; null until it answers. */
  models: ModelSelection | null
  onModelSelect: (role: AgentRole, alias: ModelAlias) => void

  // History
  runs: RunSummary[]
  activeRunId: string | null
  onReplayRun: (run: RunSummary) => void
  onDeleteRun: (id: string) => void
  onRenameRun: (id: string, name: string | null) => void
}

export function Sidebar({
  incidents,
  selectedIncidentId,
  onSelectIncident,
  onRun,
  onStop,
  status,
  mode,
  agentOk,
  agentLabel,
  skills,
  enabledSkills,
  onToggleSkill,
  mcpServers,
  enabledServers,
  onToggleServer,
  models,
  onModelSelect,
  runs,
  activeRunId,
  onReplayRun,
  onDeleteRun,
  onRenameRun,
}: SidebarProps) {
  // Only a live run locks the controls. Following another dashboard's run
  // from history is read-only and can be left at any time.
  const running = status === "running" && mode === "live"
  const canRun = !!selectedIncidentId && agentOk
  const [incidentsOpen, setIncidentsOpen] = useState(false)

  return (
    <SidebarRoot collapsible="offcanvas">
      <SidebarHeader className="flex-row items-center justify-between px-4 pt-4">
        <div className="flex items-center gap-2 font-semibold tracking-tight">
          <LensesLogo className="size-4 text-primary" />
          Kafka SRE Agent
        </div>
        <CollapseButton />
      </SidebarHeader>

      <SidebarSeparator className="mx-0" />

      <SidebarContent>
        <div className="pt-1">
          <IncidentsList
            incidents={incidents}
            selectedId={selectedIncidentId}
            onSelect={onSelectIncident}
            disabled={running}
            open={incidentsOpen}
            onToggle={() => setIncidentsOpen((v) => !v)}
          />
          <SidebarGroup className="py-1">
            {running ? (
              <Button variant="destructive" className="w-full" onClick={onStop}>
                <Square className="size-4" /> Stop
              </Button>
            ) : (
              <Button className="w-full" onClick={onRun} disabled={!canRun}>
                <Play className="size-4" /> Run on selected incident
              </Button>
            )}
          </SidebarGroup>
        </div>

        <SidebarSeparator className="mx-0" />

        <McpServersList
          servers={mcpServers}
          enabled={enabledServers}
          onToggle={onToggleServer}
          disabled={running}
        />

        <SidebarSeparator className="mx-0" />

        <SkillsList
          skills={skills}
          enabled={enabledSkills}
          onToggle={onToggleSkill}
          disabled={running}
        />

        <SidebarSeparator className="mx-0" />

        <ModelSettings
          models={models}
          onSelect={onModelSelect}
          disabled={running}
        />

        <SidebarSeparator className="mx-0" />

        <RunHistoryList
          runs={runs}
          activeRunId={activeRunId}
          onReplay={onReplayRun}
          onDelete={onDeleteRun}
          onRename={onRenameRun}
          disabled={running}
        />
      </SidebarContent>

      <SidebarSeparator className="mx-0" />

      <SidebarFooter className="flex-row items-center gap-2 px-4 py-3 text-xs">
        <StatusDot
          tone={agentOk ? "success" : "destructive"}
          pulse={agentOk}
        />
        <span className="truncate text-muted-foreground">{agentLabel}</span>
        <span className="ml-auto">
          <ModeToggle />
        </span>
      </SidebarFooter>

      <SidebarRail />
    </SidebarRoot>
  )
}

function CollapseButton() {
  const { toggleSidebar } = useSidebar()
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          size="icon-sm"
          variant="ghost"
          onClick={toggleSidebar}
          className="-mr-1 text-muted-foreground hover:text-foreground"
          aria-label="Collapse sidebar"
        >
          <PanelLeftClose className="size-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="flex items-center gap-2">
        Collapse
        <Kbd>[</Kbd>
      </TooltipContent>
    </Tooltip>
  )
}
