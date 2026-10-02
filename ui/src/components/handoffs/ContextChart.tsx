import { useLayoutEffect, useRef, useState } from "react"
import { formatTokens } from "@/lib/format"
import { ROOT_CALL_ID, type AgentCall, type ModelCall } from "@/lib/handoffs"
import { cn } from "@/lib/utils"
import { sourceStyle } from "@/components/tools/subagent-styles"

/**
 * An agent call's context window as bars, one per model call: the prompt it
 * sent each time, cached reads included. Scaled to ``max`` when given (to
 * compare calls), else to the call's own peak.
 */
export function ContextBars({
  modelCalls,
  accent,
  max,
  height = 18,
  barWidth = 4,
  className,
}: {
  modelCalls: ModelCall[]
  accent: string
  max?: number
  height?: number
  barWidth?: number
  className?: string
}) {
  if (modelCalls.length === 0) return null
  const top = max ?? Math.max(...modelCalls.map((m) => m.inputTokens))
  return (
    <span
      className={cn("inline-flex items-end gap-0.5", className)}
      style={{ height }}
      role="img"
      aria-label={`Context per model call: ${modelCalls.map((m) => formatTokens(m.inputTokens)).join(", ")} tokens`}
    >
      {modelCalls.map((m, i) => (
        <span
          key={i}
          className="rounded-[1px]"
          title={`Model call ${i + 1}: ${m.inputTokens.toLocaleString("en-US")} tokens in context`}
          style={{
            width: barWidth,
            height: Math.max(2, (m.inputTokens / (top || 1)) * height),
            background: accent,
            opacity: 0.35 + 0.65 * ((i + 1) / modelCalls.length),
          }}
        />
      ))}
    </span>
  )
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw))
  const n = raw / p
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p
}

const TIME_STEPS_S = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800]

function clock(ms: number): string {
  const s = Math.round(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

interface Point {
  call: AgentCall
  index: number
  x: number
  y: number
  m: ModelCall
}

/**
 * Every agent's context window over the run: one line per agent call, a dot
 * per model call. The supervisor's line stays low - it only ever holds
 * briefs and answers - while a specialist's climbs as tool output piles up.
 */
export function ContextChart({
  calls,
  start,
  end,
  height = 200,
  compact = false,
  selectedId = null,
  onSelect,
}: {
  calls: AgentCall[]
  start: number
  end: number
  height?: number
  /** Smaller type and legend, for the right panel. */
  compact?: boolean
  selectedId?: string | null
  onSelect?: (callId: string) => void
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<Point | null>(null)

  const pad = compact
    ? { l: 34, r: 8, t: 8, b: 18 }
    : { l: 44, r: 12, t: 10, b: 22 }
  const plotW = Math.max(0, width - pad.l - pad.r)
  const plotH = height - pad.t - pad.b

  const peak = Math.max(0, ...calls.flatMap((c) => c.modelCalls.map((m) => m.inputTokens)))
  const yStep = niceStep(Math.max(peak, 1000) / 4)
  const yMax = Math.ceil((peak * 1.05) / yStep) * yStep || yStep
  const span = Math.max(end - start, 1000)
  const tStep =
    (TIME_STEPS_S.find((s) => span / (s * 1000) <= (compact ? 4 : 7)) ?? 3600) * 1000

  const x = (at: number) => pad.l + ((at - start) / span) * plotW
  const y = (tokens: number) => pad.t + plotH - (tokens / yMax) * plotH

  const series = calls
    .filter((c) => c.modelCalls.length > 0)
    .map((call) => ({
      call,
      points: call.modelCalls.map(
        (m, index): Point => ({ call, index, m, x: x(m.at), y: y(m.inputTokens) }),
      ),
    }))

  // One legend entry per agent, with its peak across calls.
  const peakBySource = new Map<string, number>()
  for (const c of calls) {
    for (const m of c.modelCalls) {
      peakBySource.set(c.source, Math.max(peakBySource.get(c.source) ?? 0, m.inputTokens))
    }
  }

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    let best: Point | null = null
    let bestD = 24 ** 2
    for (const s of series) {
      for (const p of s.points) {
        const d = (p.x - mx) ** 2 + (p.y - my) ** 2
        if (d < bestD) {
          bestD = d
          best = p
        }
      }
    }
    setHover(best)
  }

  const yTicks: number[] = []
  for (let v = 0; v <= yMax; v += yStep) yTicks.push(v)
  const tTicks: number[] = []
  for (let t = 0; t <= span; t += tStep) tTicks.push(t)

  const fontSize = compact ? 9 : 10
  return (
    <div className="space-y-2">
      <div ref={ref} className="relative" style={{ height }}>
        {width > 0 && (
          <svg
            width={width}
            height={height}
            className="block overflow-visible"
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
            onClick={() => hover && onSelect?.(hover.call.id)}
            style={{ cursor: hover && onSelect ? "pointer" : undefined }}
          >
            {yTicks.map((v) => (
              <g key={v}>
                <line
                  x1={pad.l}
                  x2={pad.l + plotW}
                  y1={y(v)}
                  y2={y(v)}
                  stroke="var(--border)"
                  strokeDasharray={v === 0 ? undefined : "2 3"}
                />
                <text
                  x={pad.l - 6}
                  y={y(v)}
                  dy="0.32em"
                  textAnchor="end"
                  fontSize={fontSize}
                  className="fill-muted-foreground tabular-nums"
                >
                  {formatTokens(v)}
                </text>
              </g>
            ))}
            {tTicks.map((t) => (
              <text
                key={t}
                x={x(start + t)}
                y={height - 4}
                textAnchor="middle"
                fontSize={fontSize}
                className="fill-muted-foreground tabular-nums"
              >
                {clock(t)}
              </text>
            ))}
            {series.map(({ call, points }) => {
              const accent = sourceStyle(call.source).accent
              const isRoot = call.id === ROOT_CALL_ID
              const dim = selectedId != null && selectedId !== call.id
              return (
                <g
                  key={call.id}
                  opacity={dim ? 0.25 : 1}
                  style={{ transition: "opacity 200ms" }}
                >
                  <polyline
                    points={points.map((p) => `${p.x},${p.y}`).join(" ")}
                    fill="none"
                    stroke={accent}
                    strokeWidth={isRoot ? 2.5 : 1.75}
                    strokeDasharray={isRoot ? "5 3" : undefined}
                    strokeLinejoin="round"
                  />
                  {points.map((p) => (
                    <circle
                      key={p.index}
                      cx={p.x}
                      cy={p.y}
                      r={hover === p ? 4.5 : compact ? 2 : 2.75}
                      fill={accent}
                    />
                  ))}
                </g>
              )
            })}
          </svg>
        )}
        {hover && (
          <div
            className="pointer-events-none absolute z-10 rounded-md border bg-popover px-2 py-1 text-xs whitespace-nowrap text-popover-foreground shadow-md"
            style={{
              left: Math.min(hover.x + 10, Math.max(0, width - 190)),
              top: Math.max(0, hover.y - 46),
            }}
          >
            <div className="font-medium" style={{ color: sourceStyle(hover.call.source).accent }}>
              {sourceStyle(hover.call.source).label} · model call {hover.index + 1}
            </div>
            <div className="tabular-nums">
              {hover.m.inputTokens.toLocaleString("en-US")} tokens in context
            </div>
            <div className="text-muted-foreground tabular-nums">
              at {clock(hover.m.at - start)}
            </div>
          </div>
        )}
      </div>
      <ul className={cn("flex flex-wrap gap-x-4 gap-y-1", compact ? "text-[11px]" : "text-xs")}>
        {[...peakBySource].map(([source, top]) => {
          const style = sourceStyle(source)
          return (
            <li key={source} className="flex items-center gap-1.5">
              <span
                className={cn("h-0.5 w-3 rounded-full", source === "supervisor" && "w-3.5")}
                style={{ background: style.accent }}
              />
              <span className="text-muted-foreground">{compact ? style.short : style.label}</span>
              <span className="font-mono tabular-nums">{formatTokens(top)}</span>
              {!compact && <span className="text-muted-foreground">peak</span>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
