import { ChevronRight } from "lucide-react"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
} from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"

interface SidebarSectionProps {
  label: string
  icon?: React.ReactNode
  /** Right-aligned trigger slot (count pill, toggle, ...). */
  meta?: React.ReactNode
  /** Uncontrolled initial state. */
  defaultOpen?: boolean
  /** Controlled mode. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  disabled?: boolean
  className?: string
  children: React.ReactNode
}

/**
 * Collapsible sidebar section: SidebarGroup whose label row is a
 * CollapsibleTrigger. Replaces the six hand-rolled useState+Chevron section
 * headers (Incidents, MCP servers, Skills, Models, History).
 */
export function SidebarSection({
  label,
  icon,
  meta,
  defaultOpen,
  open,
  onOpenChange,
  disabled,
  className,
  children,
}: SidebarSectionProps) {
  return (
    <Collapsible
      defaultOpen={defaultOpen}
      open={open}
      onOpenChange={onOpenChange}
      disabled={disabled}
      className={cn("group/section", className)}
    >
      <SidebarGroup className="py-1">
        <SidebarGroupLabel asChild>
          <CollapsibleTrigger
            disabled={disabled}
            className="w-full gap-1.5 disabled:pointer-events-none disabled:opacity-60"
          >
            <ChevronRight className="size-3.5 shrink-0 transition-transform group-data-[state=open]/section:rotate-90" />
            {icon}
            <span className="truncate text-xs tracking-wider uppercase">
              {label}
            </span>
            {meta != null && (
              <span className="ml-auto flex shrink-0 items-center gap-1.5">
                {meta}
              </span>
            )}
          </CollapsibleTrigger>
        </SidebarGroupLabel>
        <CollapsibleContent>
          <SidebarGroupContent className="pt-1.5">{children}</SidebarGroupContent>
        </CollapsibleContent>
      </SidebarGroup>
    </Collapsible>
  )
}
