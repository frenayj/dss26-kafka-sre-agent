import { ChevronRight } from "lucide-react"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

interface ExpanderProps {
  /** Trigger row content (left side, next to the chevron). */
  label: React.ReactNode
  /** Optional right-aligned trigger content (counts, actions). */
  meta?: React.ReactNode
  /** Uncontrolled initial state. */
  defaultOpen?: boolean
  /** Controlled mode. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  disabled?: boolean
  className?: string
  triggerClassName?: string
  contentClassName?: string
  children: React.ReactNode
}

/**
 * Chevron-toggled section built on Collapsible. Replaces the six hand-rolled
 * useState/`<details>` expander patterns (sidebar sections, ToolCard
 * INPUT/RESULT, AvroSchema raw, ConnectorDefinition yaml, TopicList internal
 * topics, SqlQuery metadata).
 */
export function Expander({
  label,
  meta,
  defaultOpen,
  open,
  onOpenChange,
  disabled,
  className,
  triggerClassName,
  contentClassName,
  children,
}: ExpanderProps) {
  return (
    <Collapsible
      defaultOpen={defaultOpen}
      open={open}
      onOpenChange={onOpenChange}
      disabled={disabled}
      className={className}
    >
      <CollapsibleTrigger
        className={cn(
          "group/expander flex w-full min-w-0 items-center gap-1.5 rounded-sm text-xs tracking-wider text-muted-foreground uppercase transition-colors hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-60",
          triggerClassName,
        )}
      >
        <ChevronRight className="size-3 shrink-0 transition-transform group-data-[state=open]/expander:rotate-90" />
        {label}
        {meta != null && (
          <span className="ml-auto flex shrink-0 items-center gap-1.5 normal-case">
            {meta}
          </span>
        )}
      </CollapsibleTrigger>
      <CollapsibleContent className={cn("pt-1.5", contentClassName)}>
        {children}
      </CollapsibleContent>
    </Collapsible>
  )
}
