/** Lenses MCP result parsing + shared formatting / tone helpers. */

import type { Tone } from "@/components/shared/tone"

/** Parse a JSON tool result string into a typed object. */
export function parseToolResult<T>(
  result: string,
  requiredKeys?: string[],
): { ok: true; data: T } | { ok: false } {
  try {
    const data = JSON.parse(result) as T
    if (typeof data !== "object" || data === null) return { ok: false }
    if (Array.isArray(data)) return { ok: false }
    if (requiredKeys) {
      const obj = data as Record<string, unknown>
      for (const key of requiredKeys) {
        if (obj[key] === undefined) return { ok: false }
      }
    }
    return { ok: true, data }
  } catch {
    return { ok: false }
  }
}

/** Parse a JSON tool result string that returns a top-level array. */
export function parseArrayToolResult<T>(
  result: string,
): { ok: true; data: T[] } | { ok: false } {
  try {
    const data = JSON.parse(result)
    if (!Array.isArray(data)) return { ok: false }
    return { ok: true, data: data as T[] }
  } catch {
    return { ok: false }
  }
}

/**
 * A Lenses topic tag. The MCP returns objects (``{ name: "domain:cards" }``)
 * but older payloads / other endpoints may send bare strings, so accept both.
 */
export type TopicTag = string | { name?: string; [key: string]: unknown }

/** Normalize a topic tag to its display label. */
export function tagLabel(tag: TopicTag): string {
  if (typeof tag === "string") return tag
  if (tag && typeof tag.name === "string") return tag.name
  return ""
}

export interface AvroField {
  name: string
  type: unknown
  doc?: string
  default?: unknown
}

/** Pull the ``fields`` array out of a serialized Avro record schema. Returns
 *  null for primitive schemas (e.g. ``"string"``) or unparseable input. */
export function extractAvroFields(schemaStr?: string | null): AvroField[] | null {
  if (!schemaStr) return null
  try {
    const parsed = JSON.parse(schemaStr)
    if (
      parsed &&
      typeof parsed === "object" &&
      "fields" in parsed &&
      Array.isArray((parsed as { fields: unknown }).fields)
    ) {
      return (parsed as { fields: AvroField[] }).fields
    }
    return null
  } catch {
    return null
  }
}

/** Bytes → human-readable. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`
  return `${bytes} B`
}

/** Counts → compact (12.3k / 4.5M). */
export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

/** Lag → semantic tone for StatusBadge / Meter / StatTile. */
export function lagToTone(lag: number): Tone {
  if (lag > 100_000) return "destructive"
  if (lag > 1_000) return "warning"
  return "success"
}

/** Consumer-group / connector / task state → semantic tone. */
export function stateToTone(state: string): Tone {
  const s = state.toLowerCase()
  switch (s) {
    case "running":
    case "stable":
      return "success"
    case "rebalancing":
    case "paused":
    case "degraded":
      return "warning"
    case "failed":
    case "dead":
    case "empty":
    case "unassigned":
      return "destructive"
    default:
      if (s.includes("noactive")) return "destructive"
      return "muted"
  }
}

/** Incident severity (P1/P2/P3...) → semantic tone. */
export function severityToTone(severity: string): Tone {
  switch (severity.toUpperCase()) {
    case "P1":
      return "destructive"
    case "P2":
      return "warning"
    default:
      return "info"
  }
}
