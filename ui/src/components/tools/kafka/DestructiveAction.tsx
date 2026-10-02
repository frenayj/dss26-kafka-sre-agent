import { Check, X } from "lucide-react"
import { Callout } from "@/components/shared/callout"
import { parseToolResult } from "./parse"
import type { DestructiveActionData } from "./types"

interface Props {
  result: string
}

export function DestructiveAction({ result }: Props) {
  const parsed = parseToolResult<DestructiveActionData>(result, ["success"])
  if (!parsed.ok) return null
  const d = parsed.data
  const ok = d.success !== false

  return (
    <div className="space-y-2.5">
      <Callout
        variant={ok ? "success" : "destructive"}
        size="sm"
        icon={ok ? <Check className="size-3.5" /> : <X className="size-3.5" />}
        title={ok ? "Action succeeded" : "Action failed"}
      />

      {d.message && (
        <p className="text-xs text-foreground leading-relaxed px-1">{d.message}</p>
      )}
    </div>
  )
}
