import { cn } from "@/lib/utils"

interface KeyValueRow {
  key: React.ReactNode
  value: React.ReactNode
  /** Highlight this row (e.g. overridden config). */
  accent?: boolean
}

interface KeyValueListProps extends React.ComponentProps<"div"> {
  rows: KeyValueRow[]
}

/**
 * Bordered key/value row list. Replaces the six hand-rolled "list tables"
 * (TopicDetail config, AvroSchema fields, ConnectorDefinition config, ...).
 */
export function KeyValueList({ rows, className, ...props }: KeyValueListProps) {
  return (
    <div
      data-slot="key-value-list"
      className={cn(
        "divide-y divide-border/60 overflow-hidden rounded-md border border-border/60",
        className,
      )}
      {...props}
    >
      {rows.map((row, idx) => (
        <div
          key={idx}
          className={cn(
            "flex items-center justify-between gap-3 px-2.5 py-1.5",
            row.accent && "bg-warning/10",
          )}
        >
          <span className="min-w-0 truncate font-mono text-xs font-medium">
            {row.key}
          </span>
          <span className="min-w-0 truncate text-right font-mono text-xs text-muted-foreground">
            {row.value}
          </span>
        </div>
      ))}
    </div>
  )
}
