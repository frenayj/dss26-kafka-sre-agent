import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react"
import { cn } from "@/lib/utils"
import type { ArchEdgeData } from "./types"

/**
 * Smooth-step edge with three presentation states (idle / active / dim) and a
 * moving pulse dot while active - the "data flowing" cue in scenario mode. The
 * pulse runs source -> target, or back with ``pulse: "toSource"``.
 */
export function FlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<Edge<ArchEdgeData, "flow">>) {
  let path: string
  let labelX: number
  let labelY: number
  if (data?.turnX != null) {
    // Horizontal-vertical-horizontal route with the vertical segment pinned
    // to turnX (a group gutter), instead of smoothstep's midpoint bend.
    const r = 14
    const tx = data.turnX
    const dx1 = Math.sign(tx - sourceX) || 1
    const dy = Math.sign(targetY - sourceY) || 1
    const dx2 = Math.sign(targetX - tx) || 1
    path = [
      `M ${sourceX} ${sourceY}`,
      `L ${tx - r * dx1} ${sourceY}`,
      `Q ${tx} ${sourceY} ${tx} ${sourceY + r * dy}`,
      `L ${tx} ${targetY - r * dy}`,
      `Q ${tx} ${targetY} ${tx + r * dx2} ${targetY}`,
      `L ${targetX} ${targetY}`,
    ].join(" ")
    labelX = tx
    labelY = (sourceY + targetY) / 2
  } else {
    ;[path, labelX, labelY] = getSmoothStepPath({
      sourceX,
      sourceY,
      targetX,
      targetY,
      sourcePosition,
      targetPosition,
      borderRadius: 14,
    })
  }

  const state = data?.state ?? "idle"
  // The pulse follows the data, which for a read runs back to the caller.
  const motion =
    data?.pulse === "toSource"
      ? { keyPoints: "1;0", keyTimes: "0;1", calcMode: "linear" }
      : {}
  const accent = data?.accent ?? "var(--primary)"
  const stroke = state === "active" ? accent : "var(--muted-foreground)"
  const strokeOpacity = state === "active" ? 0.9 : state === "dim" ? 0.07 : 0.35

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke,
          strokeOpacity,
          strokeWidth: state === "active" ? 2 : 1.25,
          strokeDasharray: data?.dashed ? "5 5" : undefined,
          transition: "stroke-opacity 400ms, stroke 400ms",
        }}
      />
      {state === "active" && (
        <>
          <circle r="3.5" fill={accent}>
            <animateMotion dur="1.5s" repeatCount="indefinite" path={path} {...motion} />
          </circle>
          <circle r="6" fill={accent} opacity="0.25">
            <animateMotion dur="1.5s" repeatCount="indefinite" path={path} {...motion} />
          </circle>
        </>
      )}
      {data?.label && state !== "dim" && (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "nodrag nopan pointer-events-none absolute rounded border bg-background px-1.5 py-0.5 text-[10px] leading-none shadow-sm",
              state === "active"
                ? "font-medium text-foreground"
                : "text-muted-foreground",
            )}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              // Above the edge lines (svg layers at z 1 / 3, which sit above
              // the label layer once elevated); active labels above cards too.
              zIndex: state === "active" ? 4 : 2,
              borderColor:
                state === "active"
                  ? `color-mix(in oklch, ${accent} 55%, transparent)`
                  : undefined,
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}
