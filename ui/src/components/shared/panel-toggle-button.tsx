import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface PanelToggleButtonProps
  extends React.ComponentProps<typeof Button> {
  /** Tooltip label ("Open right panel"). */
  label: string
  /** Keyboard shortcut hint rendered as a Kbd chip. */
  shortcut?: string
  tooltipSide?: "top" | "bottom" | "left" | "right"
}

/** Ghost icon button with a tooltip + shortcut hint for panel toggles. */
export function PanelToggleButton({
  label,
  shortcut,
  tooltipSide = "bottom",
  children,
  ...props
}: PanelToggleButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          className="text-muted-foreground hover:text-foreground"
          {...props}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side={tooltipSide} className="flex items-center gap-2">
        {label}
        {shortcut && <Kbd>{shortcut}</Kbd>}
      </TooltipContent>
    </Tooltip>
  )
}
