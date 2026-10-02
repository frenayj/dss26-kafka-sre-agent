import { useCallback, useEffect, useState } from "react"
import { fetchIncidents } from "@/lib/api"
import type { IncidentSummary } from "@/lib/api"

const POLL_MS = 4_000

/** Poll-driven view of the incidents queue.
 *
 *  4-second cadence is fast enough to look "live" for a webhook flow
 *  without flooding the server. Callers can trigger an immediate refetch
 *  via the returned ``refetch`` (used after a run finishes to mark an
 *  incident as completed).
 */
export function useIncidents() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(async () => {
    try {
      const res = await fetchIncidents()
      setIncidents(res.incidents)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const res = await fetchIncidents()
        if (!cancelled) {
          setIncidents(res.incidents)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      }
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return { incidents, error, refetch }
}
