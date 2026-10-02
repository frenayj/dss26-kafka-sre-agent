import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { cn } from "@/lib/utils"

interface EmptyStateProps
  extends Omit<React.ComponentProps<typeof Empty>, "title"> {
  icon?: React.ReactNode
  title: React.ReactNode
  description?: React.ReactNode
}

/**
 * Compact Empty preset for lists and panels ("No past runs yet."). The stock
 * Empty is sized for full pages; this keeps its anatomy at card scale.
 */
export function EmptyState({
  icon,
  title,
  description,
  className,
  children,
  ...props
}: EmptyStateProps) {
  return (
    <Empty
      className={cn("gap-2 border border-dashed border-border/60 p-4 md:p-5", className)}
      {...props}
    >
      <EmptyHeader className="gap-1">
        {icon != null && (
          <EmptyMedia
            variant="icon"
            className="mb-0 size-8 [&_svg:not([class*='size-'])]:size-4"
          >
            {icon}
          </EmptyMedia>
        )}
        <EmptyTitle className="text-sm font-medium">{title}</EmptyTitle>
        {description != null && (
          <EmptyDescription className="text-xs">{description}</EmptyDescription>
        )}
      </EmptyHeader>
      {children}
    </Empty>
  )
}
