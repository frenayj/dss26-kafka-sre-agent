import { useMemo } from "react"
import { cn } from "@/lib/utils"

interface DiffViewProps {
  content: string
  maxHeight?: string
}

interface DiffLine {
  kind: "add" | "del" | "header" | "hunk" | "ctx" | "meta"
  text: string
}

function classify(line: string): DiffLine["kind"] {
  if (line.startsWith("+++") || line.startsWith("---")) return "header"
  if (line.startsWith("@@")) return "hunk"
  if (line.startsWith("diff ") || line.startsWith("index ")) return "meta"
  if (line.startsWith("+")) return "add"
  if (line.startsWith("-")) return "del"
  return "ctx"
}

const LINE_CLASSES: Record<DiffLine["kind"], string> = {
  add: "bg-success/15 text-success-foreground",
  del: "bg-destructive/15 text-destructive-foreground",
  header: "text-info font-medium",
  hunk: "text-warning",
  meta: "text-muted-foreground",
  ctx: "",
}

export function DiffView({ content, maxHeight = "28rem" }: DiffViewProps) {
  const lines = useMemo(
    () => content.split("\n").map<DiffLine>((text) => ({ kind: classify(text), text })),
    [content],
  )

  return (
    <div
      className="mac-scrollbar overflow-auto rounded-md border border-border/50 bg-muted/40 font-mono text-xs whitespace-pre"
      style={{ maxHeight }}
    >
      {lines.map((line, i) => (
        <div key={i} className={cn("px-2 py-0.5", LINE_CLASSES[line.kind])}>
          {line.text || " "}
        </div>
      ))}
    </div>
  )
}
