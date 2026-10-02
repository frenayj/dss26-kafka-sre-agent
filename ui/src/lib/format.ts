/** Shared formatting helpers. */

/** Token counts → compact display (999, 1.2k, 45k, 1.3M). */
export function formatTokens(n: number): string {
  if (n < 1000) return n.toString()
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}

/** Milliseconds → compact display (850ms, 2.3s). */
export function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/** Epoch ms → "12s ago" / "3m ago" / "2h ago" / "5d ago". */
export function relativeTime(ms: number): string {
  const diff = Date.now() - ms
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const d = Math.floor(hr / 24)
  return `${d}d ago`
}

/** Start/end timestamps → "12.3s", or null while still pending. */
export function elapsedSeconds(
  startedAt?: number | null,
  completedAt?: number | null,
): string | null {
  if (startedAt && completedAt) {
    return `${((completedAt - startedAt) / 1000).toFixed(1)}s`
  }
  return null
}

/** Lenient JSON parse for tool payloads that may be prose or JSON. */
export function safeParseJson(s: string): Record<string, unknown> | null {
  try {
    const v = JSON.parse(s)
    return typeof v === "object" && v !== null && !Array.isArray(v)
      ? (v as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}
