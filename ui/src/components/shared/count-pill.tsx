import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

/** Small numeric pill shown next to section headers ("Topics 32"). */
export function CountPill({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <Badge
      variant="secondary"
      className={cn("px-1.5 font-mono text-xs tabular-nums", className)}
      {...props}
    />
  )
}
