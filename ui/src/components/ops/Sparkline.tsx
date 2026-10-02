import { TONE_BG, TONE_TEXT, type Tone } from "@/components/shared/tone"
import { cn } from "@/lib/utils"

// Drawing box in viewBox units. The SVG stretches to its container
// (preserveAspectRatio="none"), so strokes use non-scaling-stroke and the end
// dot is an HTML element positioned in percent - neither distorts.
const W = 100
const H = 32
const PAD = 3

interface SparklineProps {
  values: number[]
  /** Slots across the width: the line grows in from the right until full. */
  capacity: number
  /** Reference value drawn as a hairline (the healthy/unhealthy boundary). */
  threshold?: number
  tone: Tone
  label: string
  className?: string
}

/** Tiny single-series trend line with an area wash and a dot on the latest value. */
export function Sparkline({
  values,
  capacity,
  threshold,
  tone,
  label,
  className,
}: SparklineProps) {
  if (values.length === 0) return null

  // Keep the threshold in range so a flat, healthy line still reads as
  // "well below the line" rather than filling the box.
  const max = Math.max(...values, threshold ?? 0, 1) * 1.1
  const slots = Math.max(capacity, values.length, 2)
  const x = (i: number) => ((slots - values.length + i) / (slots - 1)) * W
  const y = (v: number) => H - PAD - (v / max) * (H - 2 * PAD)

  // A single sample draws no line; the end dot alone shows it.
  const line = values.map((v, i) => `${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(" ")
  const area = `${x(0).toFixed(2)},${H} ${line} ${W},${H}`
  const last = values[values.length - 1]
  const summary = `${label}: last ${values.length} samples, min ${Math.min(...values).toLocaleString()}, max ${Math.max(...values).toLocaleString()}`

  return (
    <div className={cn("relative mr-1", className)} title={summary}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className={cn("block h-full w-full overflow-visible", TONE_TEXT[tone])}
        role="img"
        aria-label={summary}
      >
        {threshold !== undefined && (
          <line
            x1={0}
            x2={W}
            y1={y(threshold)}
            y2={y(threshold)}
            className="stroke-muted-foreground/30"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        )}
        <polygon points={area} fill="currentColor" fillOpacity={0.1} />
        <polyline
          points={line}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <span
        className={cn(
          "absolute right-0 size-2 translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card",
          TONE_BG[tone],
        )}
        style={{ top: `${(y(last) / H) * 100}%` }}
      />
    </div>
  )
}
