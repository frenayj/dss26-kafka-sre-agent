import { cn } from "@/lib/utils"
import { TONE_BG, type Tone } from "./tone"

const SIZE = {
  sm: "size-1.5",
  default: "size-2",
  lg: "size-3",
} as const

interface StatusDotProps extends React.ComponentProps<"span"> {
  tone: Tone
  size?: keyof typeof SIZE
  /** Slow opacity pulse for "live" indicators. */
  pulse?: boolean
}

export function StatusDot({
  tone,
  size = "default",
  pulse = false,
  className,
  ...props
}: StatusDotProps) {
  return (
    <span
      data-slot="status-dot"
      className={cn(
        "inline-block shrink-0 rounded-full",
        SIZE[size],
        TONE_BG[tone],
        pulse && "animate-pulse-slow",
        className,
      )}
      {...props}
    />
  )
}
