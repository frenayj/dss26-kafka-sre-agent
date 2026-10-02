import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { cn } from "@/lib/utils"

type CalloutVariant = "default" | "destructive" | "warning" | "success" | "info"

interface CalloutProps
  extends Omit<React.ComponentProps<typeof Alert>, "title"> {
  variant?: CalloutVariant
  icon?: React.ReactNode
  title?: React.ReactNode
  /** Compact paddings for use inside tool cards. */
  size?: "sm" | "default"
}

/**
 * Status banner built on Alert. Replaces the hand-rolled success/error
 * banners in ValidationResult, DestructiveAction, EnvironmentHealth and the
 * EventStream error node.
 */
export function Callout({
  variant = "default",
  icon,
  title,
  size = "default",
  className,
  children,
  ...props
}: CalloutProps) {
  return (
    <Alert
      variant={variant}
      className={cn(size === "sm" && "gap-y-0 rounded-md px-3 py-2", className)}
      {...props}
    >
      {icon}
      {title != null && (
        <AlertTitle className={cn(size === "sm" && "text-xs font-semibold")}>
          {title}
        </AlertTitle>
      )}
      {children != null && (
        <AlertDescription className={cn(size === "sm" && "text-xs")}>
          {children}
        </AlertDescription>
      )}
    </Alert>
  )
}
