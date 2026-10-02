import type { ComponentType } from "react"
import type { Edge, Node } from "@xyflow/react"

/** Icon component contract shared by lucide icons and the Lenses brand SVGs. */
export type NodeIcon = ComponentType<{ className?: string }>

export type ArchNodeKind =
  | "actor"
  | "artifact"
  | "agent"
  | "skills"
  | "mcp"
  | "system"
  | "gateway"

/**
 * Data for a diagram card. Must stay a `type` literal (not an interface) so it
 * satisfies React Flow's `Record<string, unknown>` node-data constraint.
 */
export type ArchNodeData = {
  label: string
  sublabel?: string
  icon: NodeIcon
  kind: ArchNodeKind
  /** CSS color expression, e.g. "var(--agent-triage)". Defaults to muted. */
  accent?: string
  /** Renders a pulsing red dot next to the label (the incident zone). */
  alert?: boolean
  /** Animates the icon while the card is lit: "ring" shakes it like a pager going off. */
  iconMotion?: "ring"
  /** Longer description for the click-to-inspect panel. */
  detail?: string
  /** Key/value facts for the inspect panel. */
  facts?: [string, string][]
  /** Scenario-mode presentation state, computed per step. */
  dimmed?: boolean
  active?: boolean
}

export type ArchGroupData = {
  label: string
  sublabel?: string
  /** Shown before the label: what the section is built with. */
  icon?: NodeIcon
  /**
   * Rendered size of the container div. Sized here (not via node
   * width/height) so React Flow still DOM-measures the node - explicit node
   * dimensions skip measurement and the group's edge handles never register.
   */
  width: number
  height: number
}

export type ArchFlowNode = Node<ArchNodeData, "arch"> | Node<ArchGroupData, "archGroup">

export type ArchEdgeData = {
  label?: string
  /** CSS color expression used when the edge is active. */
  accent?: string
  /** Dashed = model traffic (vs solid tool/data calls). */
  dashed?: boolean
  /**
   * Pin the H-V-H bend's vertical segment to this canvas x - used when the
   * default midpoint turn would land inside a group box instead of a gutter.
   */
  turnX?: number
  /**
   * Edges are drawn caller -> callee, and the scenario pulse follows the
   * data: "toSource" runs it back to the caller, for reads (cluster status
   * coming back to the MCP server) and model responses.
   */
  pulse?: "toSource"
  state?: "idle" | "active" | "dim"
}

export type ArchFlowEdge = Edge<ArchEdgeData, "flow">

/** One highlighted beat of a scenario walkthrough. */
export type ScenarioStep = {
  id: string
  title: string
  narration: string
  /** Node ids lit up during this step (everything else dims). */
  nodes: string[]
  /** Edge ids that carry the moving pulse during this step. */
  edges: string[]
  /** Optional chip shown next to the step title, e.g. a skill name. */
  badge?: string
}

export type Scenario = {
  id: string
  incidentId: string
  title: string
  alert: string
  steps: ScenarioStep[]
}
