import { Markdown } from "@/components/tools/Markdown"
import { cn } from "@/lib/utils"

interface MarkdownPanelProps {
  content: string
  className?: string
  /** Tailwind max-height class; scrolls beyond it. */
  maxHClassName?: string
}

/**
 * Markdown inside a muted, scroll-capped panel. Replaces the identical
 * wrappers in KafkaDiagnosis, ReporterResult, SkillActivation, ForensicsPr.
 */
export function MarkdownPanel({
  content,
  className,
  maxHClassName = "max-h-96",
}: MarkdownPanelProps) {
  return (
    <div
      data-slot="markdown-panel"
      className={cn(
        "mac-scrollbar overflow-auto rounded-md border border-border/50 bg-muted/30 p-3",
        maxHClassName,
        className,
      )}
    >
      <Markdown content={content} />
    </div>
  )
}
