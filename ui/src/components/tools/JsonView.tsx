import { useMemo } from "react"
import { CodeBlock } from "@/components/shared/code-block"
import { cn } from "@/lib/utils"

interface JsonViewProps {
  content: string
  className?: string
  maxHeight?: string
}

/** Pretty-print JSON, or fall back to the raw string when it isn't valid JSON. */
export function JsonView({ content, className, maxHeight = "28rem" }: JsonViewProps) {
  const formatted = useMemo(() => {
    try {
      return JSON.stringify(JSON.parse(content), null, 2)
    } catch {
      return content
    }
  }, [content])

  return (
    <CodeBlock
      maxHClassName=""
      className={cn("break-words", className)}
      style={{ maxHeight }}
    >
      {formatted}
    </CodeBlock>
  )
}
