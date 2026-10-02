import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import {
  fetchModels,
  updateModel,
  type AgentRole,
  type ModelAlias,
  type ModelSelection,
} from "@/lib/api"

const POLL_MS = 4_000

/** The server's model per role (GET /models), polled so a change made in
 *  another dashboard or the operator console shows up here too.
 *
 *  ``select`` shows the change right away and sends it; if the server
 *  refuses, the old value comes back. ``models`` is null until
 *  the server first answers. */
export function useModels() {
  const [models, setModels] = useState<ModelSelection | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Bumped on every local change, so a poll that left before it can't
  // overwrite the new value with the old one.
  const changes = useRef(0)

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      const seen = changes.current
      try {
        const next = await fetchModels()
        if (cancelled) return
        if (changes.current === seen) setModels(next)
        setError(null)
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

  const select = useCallback(async (role: AgentRole, alias: ModelAlias) => {
    const change = ++changes.current
    setModels((m) => (m ? { ...m, [role]: alias } : m))
    try {
      const next = await updateModel(role, alias)
      if (changes.current === change) setModels(next)
    } catch (err) {
      toast.error("Could not change the model", {
        description: err instanceof Error ? err.message : String(err),
      })
      // Put back what the server has.
      const current = await fetchModels().catch(() => null)
      if (current && changes.current === change) setModels(current)
    }
  }, [])

  return { models, error, select }
}
