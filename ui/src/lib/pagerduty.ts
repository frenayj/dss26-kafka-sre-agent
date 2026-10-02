// PagerDuty helpers.
//
// extractIncident: defensive extraction of a PagerDuty REST incident object
// from an incidents-store row's `payload`. The PD payload shape is mostly
// consistent but custom_details and assignments can vary; we read what's
// there and fall back to "-" placeholders for the rest.

import { safeParseJson } from "@/lib/format"

export interface PagerDutyIncident {
  number: number | null
  title: string
  description: string | null
  status: string
  urgency: string
  priority: string | null
  createdAt: string | null
  htmlUrl: string | null
  service: string | null
  serviceUrl: string | null
  escalationPolicy: string | null
  assignees: string[]
  alertSummary: string
  alertCount: number
  triggeredCount: number
}

function asObject(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

function asString(v: unknown): string | null {
  return typeof v === "string" ? v : null
}

function asNumber(v: unknown): number | null {
  return typeof v === "number" ? v : null
}

export function extractIncident(raw: unknown): PagerDutyIncident | null {
  const root = asObject(raw)
  if (!root) return null
  // The payload may already be the incident object, or it may be wrapped:
  // { incident: { ... } }. Handle both.
  const inc = asObject(root.incident) ?? root
  if (!inc.title && !inc.summary && !inc.incident_number) return null

  const service = asObject(inc.service)
  const escPolicy = asObject(inc.escalation_policy)
  const priority = asObject(inc.priority)
  const assignments = Array.isArray(inc.assignments) ? inc.assignments : []
  const counts = asObject(inc.alert_counts)

  const assignees: string[] = []
  for (const a of assignments) {
    const obj = asObject(a)
    if (!obj) continue
    const assignee = asObject(obj.assignee)
    if (!assignee) continue
    const name = asString(assignee.summary) ?? asString(assignee.name)
    if (name) assignees.push(name)
  }

  const alertCount = asNumber(counts?.all) ?? 0
  const triggeredCount = asNumber(counts?.triggered) ?? 0

  return {
    number: asNumber(inc.incident_number),
    title: asString(inc.title) ?? asString(inc.summary) ?? "Untitled incident",
    description: asString(inc.description),
    status: asString(inc.status) ?? "unknown",
    urgency: asString(inc.urgency) ?? "-",
    priority: asString(priority?.name) ?? asString(priority?.summary) ?? null,
    createdAt: asString(inc.created_at),
    htmlUrl: asString(inc.html_url) ?? asString(inc.self),
    service: asString(service?.name) ?? asString(service?.summary),
    serviceUrl: asString(service?.html_url) ?? asString(service?.self),
    escalationPolicy: asString(escPolicy?.name) ?? asString(escPolicy?.summary),
    assignees,
    alertSummary: asString(inc.title) ?? asString(inc.summary) ?? "Alert",
    alertCount,
    triggeredCount,
  }
}

/** The ``request`` object PagerDuty's hosted MCP tools take: ``{action, ...}``.
 *  Tolerates the input (or the request inside it) arriving as a JSON string. */
export function pagerDutyRequest(input: unknown): Record<string, unknown> | null {
  const obj = typeof input === "string" ? safeParseJson(input) : input
  if (!obj || typeof obj !== "object") return null
  let req = (obj as Record<string, unknown>).request
  if (typeof req === "string") req = safeParseJson(req)
  return req && typeof req === "object" ? (req as Record<string, unknown>) : null
}

/** One alert from ``browse_incidents`` ``list_alerts``: the monitor payload
 *  the alert carries (a Datadog monitor here), read defensively. */
export interface PagerDutyAlert {
  id: string | null
  summary: string
  status: string | null
  severity: string | null
  createdAt: string | null
  htmlUrl: string | null
  /** The integration that raised it ("Datadog"). */
  source: string | null
  service: string | null
  incident: string | null
  monitorName: string | null
  monitorId: string | null
  monitorUrl: string | null
  monitorQuery: string | null
  snapshotUrl: string | null
  runbookUrl: string | null
  metric: string | null
  value: number | null
  threshold: number | null
  /** "max over the last 1m", from the query's time aggregation. */
  window: string | null
  tags: Array<[string, string]>
}

function windowLabel(query: string | null, window: string | null): string | null {
  const m = query?.match(/^(\w+)\(last_(\w+)\)/)
  if (m) return `${m[1]} over the last ${m[2]}`
  return window ? window.replace(/^last_/, "last ") : null
}

export function extractAlerts(content: string): PagerDutyAlert[] {
  const root = safeParseJson(content)
  const list = Array.isArray(root?.response) ? root.response : []
  const alerts: PagerDutyAlert[] = []
  for (const item of list) {
    const a = asObject(item)
    if (!a) continue
    const body = asObject(a.body)
    const details = asObject(body?.details) ?? asObject(asObject(body?.cef_details)?.details) ?? {}
    const query = asString(details.monitor_query)
    const tags: Array<[string, string]> = []
    for (const t of Array.isArray(details.tags) ? details.tags : []) {
      if (typeof t !== "string") continue
      const i = t.indexOf(":")
      if (i > 0) tags.push([t.slice(0, i), t.slice(i + 1)])
    }
    alerts.push({
      id: asString(a.id),
      summary: asString(a.summary) ?? "Alert",
      status: asString(a.status),
      severity: asString(a.severity),
      createdAt: asString(a.created_at),
      htmlUrl: asString(a.html_url),
      source: asString(asObject(a.integration)?.summary),
      service: asString(asObject(a.service)?.summary),
      incident: asString(asObject(a.incident)?.summary),
      monitorName: asString(details.monitor_name),
      monitorId: asString(details.monitor_id) ?? (asNumber(details.monitor_id)?.toString() ?? null),
      monitorUrl: asString(details.alert_link),
      monitorQuery: query,
      snapshotUrl: asString(details.snapshot_url),
      runbookUrl: asString(details.runbook_url),
      metric: asString(details.metric),
      value: asNumber(details.metric_value),
      threshold: asNumber(details.threshold_critical),
      window: windowLabel(query, asString(details.evaluation_window)),
      tags,
    })
  }
  return alerts
}
