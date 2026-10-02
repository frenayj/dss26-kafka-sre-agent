import { useEffect } from "react"
import {
  Handle,
  Position,
  useUpdateNodeInternals,
  type Node,
  type NodeProps,
} from "@xyflow/react"
import { cn } from "@/lib/utils"
import type { ArchGroupData, ArchNodeData } from "./types"

const PORT_CLS = "!h-1.5 !w-1.5 !min-h-0 !min-w-0 !border-0 !bg-transparent"

/**
 * Invisible connection points - a source and a target on every side, so
 * edges can pick any geometry. Ids: targets l/t/rt/bt, sources r/b/ls/ts.
 */
function Ports() {
  return (
    <>
      <Handle id="l" type="target" position={Position.Left} className={PORT_CLS} />
      <Handle id="t" type="target" position={Position.Top} className={PORT_CLS} />
      <Handle id="rt" type="target" position={Position.Right} className={PORT_CLS} />
      <Handle id="bt" type="target" position={Position.Bottom} className={PORT_CLS} />
      <Handle id="r" type="source" position={Position.Right} className={PORT_CLS} />
      <Handle id="b" type="source" position={Position.Bottom} className={PORT_CLS} />
      <Handle id="ls" type="source" position={Position.Left} className={PORT_CLS} />
      <Handle id="ts" type="source" position={Position.Top} className={PORT_CLS} />
    </>
  )
}

/**
 * The one card used for every concrete node. Group identity comes from the
 * icon chip tinted with the node's accent (mirrors the chat feed's icon-chip
 * language); scenario mode drives `active` / `dimmed`.
 */
export function ArchNode({ data, selected }: NodeProps<Node<ArchNodeData, "arch">>) {
  const Icon = data.icon
  const accent = data.accent ?? "var(--muted-foreground)"
  const ringing = data.active && data.iconMotion === "ring"
  return (
    <div
      className={cn(
        "w-[232px] rounded-lg border bg-card px-3 py-2.5 shadow-sm",
        "transition-[opacity,box-shadow,border-color] duration-500",
        data.dimmed && "opacity-20",
        selected && "border-ring",
      )}
      style={
        data.active
          ? {
              borderColor: accent,
              boxShadow: `0 0 0 1px ${accent}, 0 0 26px -8px ${accent}`,
            }
          : undefined
      }
    >
      <div className="flex items-center gap-2">
        <span
          className="relative flex size-7 shrink-0 items-center justify-center rounded-md"
          style={{
            color: accent,
            backgroundColor: `color-mix(in oklch, ${accent} 14%, transparent)`,
          }}
        >
          {ringing && (
            <span
              className="absolute inset-0 animate-ping rounded-md opacity-40"
              style={{ backgroundColor: accent }}
            />
          )}
          <Icon className={cn("relative size-4", ringing && "animate-bell-ring")} />
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-[13px] leading-tight font-semibold">
              {data.label}
            </span>
            {data.alert && (
              <span className="relative flex size-2 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-destructive opacity-60" />
                <span className="relative inline-flex size-2 rounded-full bg-destructive" />
              </span>
            )}
          </div>
          {data.sublabel && (
            <div className="truncate text-[11px] leading-tight text-muted-foreground">
              {data.sublabel}
            </div>
          )}
        </div>
      </div>
      <Ports />
    </div>
  )
}

/**
 * Section container. Semi-transparent so the edge layer (which renders below
 * all nodes) stays visible through it.
 */
export function ArchGroupNode({ id, data }: NodeProps<Node<ArchGroupData, "archGroup">>) {
  const Icon = data.icon
  // Re-measure once after mount so the group's edge handles register even if
  // React Flow considered the node pre-measured.
  const updateNodeInternals = useUpdateNodeInternals()
  useEffect(() => {
    updateNodeInternals(id)
  }, [id, updateNodeInternals])
  return (
    <div
      className="rounded-xl border border-dashed border-border bg-muted/15"
      style={{ width: data.width, height: data.height }}
    >
      <div className="px-4 pt-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          {Icon && <Icon className="size-4" />}
          {data.label}
        </div>
        {data.sublabel && (
          <div className="text-[10px] text-muted-foreground/70">{data.sublabel}</div>
        )}
      </div>
      <Handle id="ts" type="source" position={Position.Top} className={PORT_CLS} />
      <Handle id="ls" type="source" position={Position.Left} className={PORT_CLS} />
      <Handle id="rt" type="target" position={Position.Right} className={PORT_CLS} />
    </div>
  )
}
