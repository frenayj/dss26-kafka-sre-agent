import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { TONE_TINT, type Tone } from "./tone"

interface StatusBadgeProps extends React.ComponentProps<"span"> {
  tone: Tone
}

/**
 * The app's severity/state pill: a Badge tinted by semantic tone.
 * Replaces the hand-rolled `SEVERITY_COLOR` / `stateBadgeClass` /
 * `LAG_STYLES` pills that were duplicated across the tool renderers.
 */
export function StatusBadge({
  tone,
  className,
  children,
  ...props
}: StatusBadgeProps) {
  return (
    <Badge
      variant="outline"
      data-tone={tone}
      className={cn(
        "border-transparent px-1.5 text-[10px] font-semibold tracking-wider uppercase",
        TONE_TINT[tone],
        className,
      )}
      {...props}
    >
      {children}
    </Badge>
  )
}
