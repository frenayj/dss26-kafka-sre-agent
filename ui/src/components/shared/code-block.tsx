import { cn } from "@/lib/utils"

interface CodeBlockProps extends React.ComponentProps<"pre"> {
  /** Tailwind max-height class; scrolls beyond it. */
  maxHClassName?: string
}

/**
 * Mono code/JSON block. Replaces the near-identical `<pre>` wrappers in
 * JsonView, GenericText, ConnectorList/Definition, AvroSchema, ToolCard and
 * RightPanel. Native overflow + .mac-scrollbar is deliberate here - dozens
 * of small blocks render per run, where ScrollArea would be overkill.
 */
export function CodeBlock({
  maxHClassName = "max-h-64",
  className,
  ...props
}: CodeBlockProps) {
  return (
    <pre
      data-slot="code-block"
      className={cn(
        "mac-scrollbar overflow-auto rounded-md border border-border/50 bg-muted/40 p-2 font-mono text-xs leading-relaxed whitespace-pre-wrap text-foreground/90",
        maxHClassName,
        className,
      )}
      {...props}
    />
  )
}
