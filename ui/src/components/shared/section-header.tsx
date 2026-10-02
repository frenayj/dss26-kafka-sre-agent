import { cn } from "@/lib/utils"
import { CountPill } from "./count-pill"

interface SectionHeaderProps
  extends Omit<React.ComponentProps<"div">, "title"> {
  title: React.ReactNode
  count?: number
  /** Right-aligned slot (actions, badges). */
  end?: React.ReactNode
}

/** In-card list header: small title + count pill (+ optional actions). */
export function SectionHeader({
  title,
  count,
  end,
  className,
  ...props
}: SectionHeaderProps) {
  return (
    <div
      data-slot="section-header"
      className={cn("flex items-center gap-2", className)}
      {...props}
    >
      <span className="text-xs font-semibold">{title}</span>
      {count != null && <CountPill>{count}</CountPill>}
      {end != null && <span className="ml-auto flex items-center gap-1.5">{end}</span>}
    </div>
  )
}
