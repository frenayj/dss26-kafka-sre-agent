import { CodeBlock } from "@/components/shared/code-block"
import { cn } from "@/lib/utils"

interface GenericTextProps {
  content: string
  className?: string
}

/** Last-resort renderer for tool results: monospace with wrapping + scroll. */
export function GenericText({ content, className }: GenericTextProps) {
  return (
    <CodeBlock maxHClassName="max-h-[28rem]" className={cn("break-words", className)}>
      {content}
    </CodeBlock>
  )
}
