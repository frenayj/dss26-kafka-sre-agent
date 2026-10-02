import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import type { Tone } from "./tone"

/* Static map so Tailwind sees the arbitrary-variant classes at build time. */
const INDICATOR: Record<Tone, string> = {
  success: "[&_[data-slot=progress-indicator]]:bg-success",
  warning: "[&_[data-slot=progress-indicator]]:bg-warning",
  destructive: "[&_[data-slot=progress-indicator]]:bg-destructive",
  info: "[&_[data-slot=progress-indicator]]:bg-info",
  muted: "[&_[data-slot=progress-indicator]]:bg-muted-foreground/60",
  primary: "[&_[data-slot=progress-indicator]]:bg-primary",
}

interface MeterProps
  extends Omit<React.ComponentProps<typeof Progress>, "value"> {
  value: number
  max?: number
  tone?: Tone
  /** Minimum rendered percentage so tiny values stay visible. */
  minPct?: number
}

/** Tone-aware Progress for lag bars / distribution meters. */
export function Meter({
  value,
  max = 100,
  tone = "primary",
  minPct = 0,
  className,
  ...props
}: MeterProps) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <Progress
      value={Math.max(minPct, pct)}
      className={cn("bg-muted", INDICATOR[tone], className)}
      {...props}
    />
  )
}
