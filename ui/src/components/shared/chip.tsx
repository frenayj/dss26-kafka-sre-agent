import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

/** Mono tag/value chip (topic tags, input args, consumer names). */
export function Chip({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "max-w-full rounded-md px-1.5 font-mono text-[11px] font-normal text-muted-foreground",
        className,
      )}
      {...props}
    />
  )
}
