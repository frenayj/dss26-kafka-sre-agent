import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  Background,
  BackgroundVariant,
  Panel,
  ReactFlow,
  useReactFlow,
  useStore,
  type NodeMouseHandler,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Crosshair,
  Maximize2,
  PanelLeft,
  Pause,
  Play,
  RotateCcw,
  X,
} from "lucide-react"
import { ModeToggle } from "@/components/mode-toggle"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import { Progress } from "@/components/ui/progress"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useTheme } from "@/components/theme-provider"
import { ArchGroupNode, ArchNode } from "@/components/architecture/nodes"
import { FlowEdge } from "@/components/architecture/edges"
import { ARCH_EDGES, ARCH_NODES } from "@/components/architecture/graph"
import { DEFAULT_SCENARIO_ID, SCENARIOS } from "@/components/architecture/scenarios"
import type { ArchNodeData, ScenarioStep } from "@/components/architecture/types"
import { cn } from "@/lib/utils"

const nodeTypes = { arch: ArchNode, archGroup: ArchGroupNode }
const edgeTypes = { flow: FlowEdge }

const AUTOPLAY_MS = 6500

const SCENARIO_LIST = Object.values(SCENARIOS)

type PageMode = "architecture" | "flow"

/** Lives inside <ReactFlow>: camera follow for scenario steps + a Fit button. */
function CanvasChrome({
  mode,
  follow,
  focusIds,
  focusKey,
}: {
  mode: PageMode
  follow: boolean
  focusIds: string[]
  focusKey: string
}) {
  const rf = useReactFlow()

  const refit = useCallback(() => {
    if (mode === "flow" && follow && focusIds.length > 0) {
      rf.fitView({
        nodes: focusIds.map((id) => ({ id })),
        duration: 700,
        padding: 0.35,
        maxZoom: 1.05,
      })
    } else {
      rf.fitView({ duration: 700, padding: 0.1 })
    }
    // focusKey encodes scenario+step; focusIds is derived from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey, mode, follow, rf])

  useEffect(refit, [refit])

  // Keep the framing when the canvas changes size: the window resizing
  // (fullscreening mid-demo) or the steps list opening and closing.
  const width = useStore((s) => s.width)
  const height = useStore((s) => s.height)
  const refitRef = useRef(refit)
  useEffect(() => {
    refitRef.current = refit
  }, [refit])
  useEffect(() => {
    if (!width || !height) return
    const t = window.setTimeout(() => refitRef.current(), 200)
    return () => window.clearTimeout(t)
  }, [width, height])

  return (
    <Panel position="bottom-right" className="!m-3">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="icon-sm"
            onClick={() => rf.fitView({ duration: 600, padding: 0.1 })}
            aria-label="Fit diagram"
          >
            <Maximize2 className="size-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">Fit diagram</TooltipContent>
      </Tooltip>
    </Panel>
  )
}

/** The scenario's steps, for jumping around. Hidden by default: the header
 *  carries the current step and the playback controls. */
function StepRail({
  scenarioId,
  onScenarioChange,
  stepIndex,
  onStepSelect,
}: {
  scenarioId: string
  onScenarioChange: (id: string) => void
  stepIndex: number
  onStepSelect: (i: number) => void
}) {
  const scenario = SCENARIOS[scenarioId]
  const steps = scenario.steps
  const activeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [stepIndex])

  return (
    <aside className="flex w-[312px] shrink-0 flex-col border-r bg-sidebar">
      <div className="space-y-2 border-b px-4 py-3">
        {/* A picker only once there is more than one scenario to pick. */}
        {SCENARIO_LIST.length > 1 ? (
          <Select value={scenarioId} onValueChange={onScenarioChange}>
            <SelectTrigger size="sm" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCENARIO_LIST.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  <span className="font-mono text-xs">{s.incidentId}</span>
                  <span>{s.title}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <div className="flex h-8 items-center gap-2 text-sm font-medium">
            <span className="font-mono text-xs">{scenario.incidentId}</span>
            <span>{scenario.title}</span>
          </div>
        )}
        <div className="text-xs text-muted-foreground">{scenario.alert}</div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {steps.map((s: ScenarioStep, i: number) => {
          const isActive = i === stepIndex
          const isDone = i < stepIndex
          return (
            <button
              key={s.id}
              ref={isActive ? activeRef : undefined}
              onClick={() => onStepSelect(i)}
              className={cn(
                "w-full rounded-md px-2 py-2 text-left transition-colors",
                isActive ? "bg-accent" : "hover:bg-accent/50",
              )}
            >
              <div className="flex items-center gap-2">
                {isDone ? (
                  <CircleCheck className="size-4.5 shrink-0 text-muted-foreground/60" />
                ) : (
                  <span
                    className={cn(
                      "flex size-4.5 shrink-0 items-center justify-center rounded-full border text-[10px] font-medium",
                      isActive
                        ? "border-primary bg-primary text-primary-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    {i + 1}
                  </span>
                )}
                <span
                  className={cn(
                    "min-w-0 truncate text-[13px]",
                    isActive ? "font-semibold" : isDone && "text-muted-foreground",
                  )}
                >
                  {s.title}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center gap-1 border-t p-3 text-[11px] text-muted-foreground">
        <Kbd>←</Kbd>
        <Kbd>→</Kbd>
        <span>steps</span>
        <span className="mx-1">·</span>
        <Kbd>space</Kbd>
        <span>autoplay</span>
        <span className="mx-1">·</span>
        <Kbd>[</Kbd>
        <span>this list</span>
      </div>
    </aside>
  )
}

function PlaybackControls({
  stepIndex,
  stepCount,
  playing,
  follow,
  railOpen,
  onToggleRail,
  onRestart,
  onPrev,
  onTogglePlay,
  onNext,
  onToggleFollow,
}: {
  stepIndex: number
  stepCount: number
  playing: boolean
  follow: boolean
  railOpen: boolean
  onToggleRail: () => void
  onRestart: () => void
  onPrev: () => void
  onTogglePlay: () => void
  onNext: () => void
  onToggleFollow: () => void
}) {
  const tip = (label: string, child: ReactNode) => (
    <Tooltip>
      <TooltipTrigger asChild>{child}</TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  )
  return (
    <div className="flex items-center gap-1">
      {tip(
        railOpen ? "Hide the steps ( [ )" : "Show the steps ( [ )",
        <Button
          variant={railOpen ? "secondary" : "ghost"}
          size="icon-sm"
          onClick={onToggleRail}
          aria-label={railOpen ? "Hide the steps" : "Show the steps"}
        >
          <PanelLeft className="size-4" />
        </Button>,
      )}
      {tip(
        "Restart",
        <Button variant="ghost" size="icon-sm" onClick={onRestart} aria-label="Restart">
          <RotateCcw className="size-4" />
        </Button>,
      )}
      {tip(
        "Previous step ( ← )",
        <Button
          variant="outline"
          size="icon-sm"
          onClick={onPrev}
          disabled={stepIndex === 0}
          aria-label="Previous step"
        >
          <ChevronLeft className="size-4" />
        </Button>,
      )}
      {tip(
        playing ? "Pause ( space )" : "Autoplay ( space )",
        <Button
          variant="outline"
          size="icon-sm"
          onClick={onTogglePlay}
          aria-label={playing ? "Pause" : "Autoplay"}
        >
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </Button>,
      )}
      {tip(
        "Next step ( → )",
        <Button
          variant="outline"
          size="icon-sm"
          onClick={onNext}
          disabled={stepIndex === stepCount - 1}
          aria-label="Next step"
        >
          <ChevronRight className="size-4" />
        </Button>,
      )}
      {tip(
        follow ? "Camera follows the step" : "Camera stays on full view",
        <Button
          variant={follow ? "secondary" : "ghost"}
          size="icon-sm"
          onClick={onToggleFollow}
          aria-label="Toggle camera follow"
        >
          <Crosshair className="size-4" />
        </Button>,
      )}
    </div>
  )
}

function DetailCard({ nodeId, onClose }: { nodeId: string; onClose: () => void }) {
  const node = ARCH_NODES.find((n) => n.id === nodeId)
  if (!node || node.type !== "arch") return null
  const data = node.data as ArchNodeData
  const Icon = data.icon
  const accent = data.accent ?? "var(--muted-foreground)"
  return (
    <div className="absolute top-3 right-3 z-10 w-[320px] rounded-lg border bg-popover p-4 shadow-lg">
      <div className="flex items-start gap-2.5">
        <span
          className="flex size-8 shrink-0 items-center justify-center rounded-md"
          style={{
            color: accent,
            backgroundColor: `color-mix(in oklch, ${accent} 14%, transparent)`,
          }}
        >
          <Icon className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-semibold">{data.label}</span>
          </div>
          {data.sublabel && (
            <div className="text-xs text-muted-foreground">{data.sublabel}</div>
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close">
          <X className="size-4" />
        </Button>
      </div>
      {data.detail && (
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
          {data.detail}
        </p>
      )}
      {data.facts && (
        <dl className="mt-3 space-y-1 border-t pt-3">
          {data.facts.map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-3 text-xs">
              <dt className="shrink-0 text-muted-foreground">{k}</dt>
              <dd className="truncate font-mono text-[11px]">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

function Legend() {
  return (
    <div className="absolute bottom-3 left-3 z-10 space-y-1.5 rounded-lg border bg-popover/90 px-3 py-2.5 text-[11px] text-muted-foreground shadow-sm backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="h-px w-6 bg-muted-foreground/60" />
        <span>tool / data call</span>
      </div>
      <div className="flex items-center gap-2">
        <span
          className="h-px w-6"
          style={{
            backgroundImage:
              "repeating-linear-gradient(90deg, var(--warning) 0 4px, transparent 4px 8px)",
          }}
        />
        <span>model traffic → LiteLLM</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="size-2.5 rounded-sm bg-[var(--agent-triage)]" />
        <span>sub-agent accent (matches the feed)</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="size-2.5 rounded-sm bg-[var(--lenses-brand)]" />
        <span>the Lenses deployment</span>
      </div>
      <div>click a node for details</div>
    </div>
  )
}

export default function ArchitecturePage() {
  const { resolvedTheme } = useTheme()
  const [mode, setMode] = useState<PageMode>("architecture")
  const [scenarioId, setScenarioId] = useState<string>(DEFAULT_SCENARIO_ID)
  const [stepIndex, setStepIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [follow, setFollow] = useState(true)
  // The steps list starts hidden in flow mode: the header shows the step.
  const [railOpen, setRailOpen] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)

  const scenario = SCENARIOS[scenarioId]
  const step = mode === "flow" ? scenario.steps[stepIndex] : null

  // Architecture mode: selecting a node lights it + its direct edges/peers.
  const highlight = useMemo(() => {
    if (mode === "flow") {
      return {
        nodes: new Set(step?.nodes ?? []),
        edges: new Set(step?.edges ?? []),
      }
    }
    if (!selected) return { nodes: new Set<string>(), edges: new Set<string>() }
    const edges = ARCH_EDGES.filter(
      (e) => e.source === selected || e.target === selected,
    )
    return {
      nodes: new Set([selected, ...edges.flatMap((e) => [e.source, e.target])]),
      edges: new Set(edges.map((e) => e.id)),
    }
  }, [mode, step, selected])

  // Explicit stacking: group containers (0) < edges (1) < cards (2) <
  // active edges (3). React Flow puts all edges below all nodes by default,
  // which buries connections under group backgrounds and cards.
  const nodes = useMemo(
    () =>
      ARCH_NODES.map((n) => {
        if (n.type === "archGroup") return n
        const data = n.data as ArchNodeData
        return {
          ...n,
          zIndex: 2,
          data: {
            ...data,
            active: highlight.nodes.has(n.id),
            dimmed: mode === "flow" && step != null && !highlight.nodes.has(n.id),
          },
        }
      }),
    [highlight, mode, step],
  )

  const edges = useMemo(
    () =>
      ARCH_EDGES.map((e) => {
        const state =
          mode === "flow" && step != null
            ? highlight.edges.has(e.id)
              ? ("active" as const)
              : ("dim" as const)
            : highlight.edges.has(e.id)
              ? ("active" as const)
              : ("idle" as const)
        return {
          ...e,
          zIndex: state === "active" ? 3 : 1,
          data: { ...e.data, state },
        }
      }),
    [highlight, mode, step],
  )

  // Autoplay: advance until the last step, then stop.
  useEffect(() => {
    if (!playing || mode !== "flow") return
    const t = window.setInterval(() => {
      setStepIndex((i) => {
        if (i >= scenario.steps.length - 1) {
          setPlaying(false)
          return i
        }
        return i + 1
      })
    }, AUTOPLAY_MS)
    return () => window.clearInterval(t)
  }, [playing, mode, scenario.steps.length])

  const gotoStep = useCallback((i: number) => {
    setPlaying(false)
    setStepIndex(i)
  }, [])

  const handleScenarioChange = useCallback((id: string) => {
    setScenarioId(id)
    setStepIndex(0)
    setPlaying(false)
  }, [])

  const handleModeChange = useCallback((value: string) => {
    // Let go of the toggle (also when the active mode is clicked again): left
    // focused, the arrow keys would move focus across it and space would
    // press it, instead of stepping and autoplay.
    ;(document.activeElement as HTMLElement | null)?.blur()
    if (value !== "architecture" && value !== "flow") return
    setMode(value)
    setPlaying(false)
    setSelected(null)
    if (value === "flow") setStepIndex(0)
  }, [])

  // Keyboard: arrows step, space toggles autoplay (flow mode), esc closes.
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
        setSelected(null)
        return
      }
      if (mode !== "flow") return
      if (e.key === "[") {
        e.preventDefault()
        setRailOpen((o) => !o)
      } else if (e.key === "ArrowRight") {
        e.preventDefault()
        setPlaying(false)
        setStepIndex((i) => Math.min(i + 1, scenario.steps.length - 1))
      } else if (e.key === "ArrowLeft") {
        e.preventDefault()
        setPlaying(false)
        setStepIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === " ") {
        e.preventDefault()
        setPlaying((p) => !p)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [mode, scenario.steps.length])

  const onNodeClick = useCallback<NodeMouseHandler>((_, node) => {
    if (node.type === "arch") setSelected(node.id)
  }, [])

  return (
    <TooltipProvider delayDuration={200}>
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <header className="shrink-0 border-b">
        <div className="flex items-center gap-3 px-4 py-2.5">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => {
              window.location.hash = "#/"
            }}
            aria-label="Back to dashboard"
          >
            <ArrowLeft className="size-4" />
          </Button>
          {step ? (
            // Flow mode: the header is the current step; hovering it shows
            // the step's narration.
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  key={step.id}
                  className="flex min-w-0 cursor-help items-center gap-2.5 animate-in fade-in duration-300"
                >
                  <span className="shrink-0 rounded-full border px-2 py-0.5 font-mono text-xs tabular-nums text-muted-foreground">
                    {stepIndex + 1}/{scenario.steps.length}
                  </span>
                  <h1 className="truncate text-base font-semibold">{step.title}</h1>
                  {step.badge && (
                    <Badge variant="secondary" className="shrink-0 font-mono text-[11px]">
                      {step.badge}
                    </Badge>
                  )}
                </div>
              </TooltipTrigger>
              <TooltipContent
                side="bottom"
                align="start"
                className="max-w-md text-[13px] leading-relaxed"
              >
                {step.narration}
              </TooltipContent>
            </Tooltip>
          ) : (
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold">How the Kafka SRE agent works</h1>
              <p className="truncate text-xs text-muted-foreground">
                Strands supervisor · 4 sub-agents-as-tools · 5 MCP servers · LiteLLM gateway
              </p>
            </div>
          )}
          <div className="ml-auto flex items-center gap-2">
            {mode === "flow" && (
              <PlaybackControls
                stepIndex={stepIndex}
                stepCount={scenario.steps.length}
                playing={playing}
                follow={follow}
                railOpen={railOpen}
                onToggleRail={() => setRailOpen((o) => !o)}
                onRestart={() => gotoStep(0)}
                onPrev={() => gotoStep(Math.max(stepIndex - 1, 0))}
                onTogglePlay={() => setPlaying((p) => !p)}
                onNext={() => gotoStep(Math.min(stepIndex + 1, scenario.steps.length - 1))}
                onToggleFollow={() => setFollow((f) => !f)}
              />
            )}
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={mode}
              onValueChange={handleModeChange}
            >
              <ToggleGroupItem value="architecture" className="px-3">
                Architecture
              </ToggleGroupItem>
              <ToggleGroupItem value="flow" className="px-3">
                Scenario flow
              </ToggleGroupItem>
            </ToggleGroup>
            <ModeToggle />
          </div>
        </div>
        {step && (
          <Progress
            value={((stepIndex + 1) / scenario.steps.length) * 100}
            className="h-0.5 rounded-none"
          />
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        {mode === "flow" && railOpen && (
          <StepRail
            scenarioId={scenarioId}
            onScenarioChange={handleScenarioChange}
            stepIndex={stepIndex}
            onStepSelect={gotoStep}
          />
        )}

        <div className="relative min-w-0 flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            colorMode={resolvedTheme}
            fitView
            fitViewOptions={{ padding: 0.1 }}
            minZoom={0.2}
            maxZoom={1.75}
            nodesDraggable={false}
            nodesConnectable={false}
            onNodeClick={onNodeClick}
            onPaneClick={() => setSelected(null)}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={26}
              size={1.5}
              color="var(--border)"
            />
            <CanvasChrome
              mode={mode}
              follow={follow}
              focusIds={step?.nodes ?? []}
              focusKey={`${scenarioId}:${step?.id ?? "none"}`}
            />
          </ReactFlow>

          {selected && <DetailCard nodeId={selected} onClose={() => setSelected(null)} />}
          {mode === "architecture" && !selected && <Legend />}
        </div>
      </div>
    </div>
    </TooltipProvider>
  )
}
