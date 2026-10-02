import { StatusBadge } from "@/components/shared/status-badge"
import { pagerDutyRequest } from "@/lib/pagerduty"
import { GenericText } from "./GenericText"

interface PagerDutyActionResultProps {
  input: unknown
  content: string
}

/**
 * ``manage_incidents`` - the agent's writes to the live PagerDuty incident.
 * The demo policy (agent/pagerduty_guard.py) only lets two through, so this
 * renders those two, plus the policy's refusal when the model tries another.
 */
export function PagerDutyActionResult({ input, content }: PagerDutyActionResultProps) {
  const req = pagerDutyRequest(input)
  const action = typeof req?.action === "string" ? req.action : null

  if (content.startsWith("Blocked by the demo's PagerDuty policy")) {
    return (
      <div className="space-y-1.5">
        <StatusBadge tone="warning">Blocked{action ? `: ${action}` : ""}</StatusBadge>
        <p className="text-xs text-muted-foreground">{content}</p>
      </div>
    )
  }

  if (action === "add_note" && typeof req?.note === "string") {
    return (
      <div className="space-y-1.5">
        <StatusBadge tone="info">Note added</StatusBadge>
        <p className="whitespace-pre-wrap rounded-md border border-border bg-card/40 px-3 py-2 text-xs">
          {req.note}
        </p>
      </div>
    )
  }

  const manage = req?.manage_request as Record<string, unknown> | undefined
  if (action === "update" && manage?.status === "acknowledged") {
    const ids = Array.isArray(manage.incident_ids) ? manage.incident_ids.join(", ") : null
    return (
      <div className="flex items-center gap-2">
        <StatusBadge tone="success">Acknowledged</StatusBadge>
        {ids && <span className="font-mono text-xs text-muted-foreground">{ids}</span>}
      </div>
    )
  }

  return <GenericText content={content} />
}
