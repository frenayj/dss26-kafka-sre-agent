// The triage sub-agent's answer to the supervisor: the JSON object its prompt
// asks for (agent/prompts/triage.md), possibly wrapped in prose or a code
// fence. parseTriage returns null unless it finds that object, so callers can
// fall back to showing the text as it came.

export interface TriageKnowledge {
  title: string
  url: string | null
  lastReviewed: string | null
  says: string | null
  conflicts: string[]
}

export interface TriageResult {
  incidentId: string | null
  severity: string | null
  title: string | null
  cluster: string | null
  consumerGroup: string | null
  topic: string | null
  downstreamTopic: string | null
  connector: string | null
  service: string | null
  serviceRepo: string | null
  summary: string | null
  knowledge: TriageKnowledge[]
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null
}

function jsonObject(text: string): Record<string, unknown> | null {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/)
  const candidate = fenced ? fenced[1] : text
  const start = candidate.indexOf("{")
  const end = candidate.lastIndexOf("}")
  if (start === -1 || end <= start) return null
  try {
    const v = JSON.parse(candidate.slice(start, end + 1))
    return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null
  } catch {
    return null
  }
}

export function parseTriage(text: string | null | undefined): TriageResult | null {
  if (!text) return null
  const o = jsonObject(text)
  // Triage's answer always names the incident and where it happened.
  if (!o || !(str(o.incident_id) || str(o.title)) || !(str(o.cluster) || str(o.service))) {
    return null
  }
  const knowledge: TriageKnowledge[] = []
  for (const k of Array.isArray(o.knowledge) ? o.knowledge : []) {
    if (!k || typeof k !== "object") continue
    const page = k as Record<string, unknown>
    const title = str(page.title)
    if (!title) continue
    knowledge.push({
      title,
      url: str(page.url),
      lastReviewed: str(page.last_reviewed),
      says: str(page.says),
      conflicts: Array.isArray(page.conflicts)
        ? page.conflicts.filter((c): c is string => typeof c === "string" && c.trim() !== "")
        : [],
    })
  }
  return {
    incidentId: str(o.incident_id),
    severity: str(o.severity),
    title: str(o.title),
    cluster: str(o.cluster),
    consumerGroup: str(o.consumer_group),
    topic: str(o.topic),
    downstreamTopic: str(o.downstream_topic),
    connector: str(o.connector),
    service: str(o.service),
    serviceRepo: str(o.service_repo),
    summary: str(o.summary),
    knowledge,
  }
}
