import { cn } from "@/lib/utils"
import { TONE_TEXT, type Tone } from "./tone"

interface StatTileProps extends React.ComponentProps<"div"> {
  label: React.ReactNode
  value: React.ReactNode
  tone?: Tone
}

/**
 * "Value over uppercase label" metric tile. Replaces the local
 * Stat/StatCell/SummaryCell/MetricCell/Box/MiniStat clones that were
 * re-implemented across ~12 tool renderers.
 */
export function StatTile({
  label,
  value,
  tone,
  className,
  ...props
}: StatTileProps) {
  return (
    <div
      data-slot="stat-tile"
      className={cn("min-w-0 px-2 py-1.5 text-center", className)}
      {...props}
    >
      <div
        className={cn(
          "truncate font-mono text-xs font-medium tabular-nums",
          tone ? TONE_TEXT[tone] : "text-foreground",
        )}
      >
        {value}
      </div>
      <div className="truncate text-[10px] tracking-wider text-muted-foreground uppercase">
        {label}
      </div>
    </div>
  )
}

/** Bordered grid of StatTiles (summary cards). */
export function StatGrid({
  className,
  cols = 4,
  ...props
}: React.ComponentProps<"div"> & { cols?: 2 | 3 | 4 }) {
  const COLS = {
    2: "grid-cols-2",
    3: "grid-cols-3",
    4: "grid-cols-4",
  } as const
  return (
    <div
      data-slot="stat-grid"
      className={cn(
        "grid gap-2 *:rounded-md *:border *:border-border/60 *:bg-card",
        COLS[cols],
        className,
      )}
      {...props}
    />
  )
}

/** Horizontal strip of StatTiles separated by hairline borders. */
export function StatStrip({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="stat-strip"
      className={cn(
        "flex *:flex-1 *:border-r *:border-border *:last:border-r-0",
        className,
      )}
      {...props}
    />
  )
}
