import { useCallback, useEffect, useState } from "react"
import { fetchRuns, deleteRun as apiDeleteRun, updateRunName as apiUpdateRunName } from "@/lib/api"
import type { RunSummary } from "@/lib/api"

const POLL_MS = 5_000

export function useRunHistory() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(async () => {
    try {
      const res = await fetchRuns()
      setRuns(res.runs)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const res = await fetchRuns()
        if (!cancelled) {
          setRuns(res.runs)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const deleteRun = useCallback(
    async (id: string) => {
      await apiDeleteRun(id)
      setRuns((prev) => prev.filter((r) => r.id !== id))
    },
    [],
  )

  const renameRun = useCallback(
    async (id: string, name: string | null) => {
      // Optimistic local update - the next poll will reconcile.
      setRuns((prev) => prev.map((r) => (r.id === id ? { ...r, name } : r)))
      try {
        await apiUpdateRunName(id, name)
      } catch (err) {
        // Re-fetch on failure to roll back the optimistic write.
        setError(err instanceof Error ? err.message : String(err))
        try {
          const res = await fetchRuns()
          setRuns(res.runs)
        } catch {
          /* swallow; the next poll will recover */
        }
      }
    },
    [],
  )

  return { runs, error, refetch, deleteRun, renameRun }
}
