import { useEffect, useState } from "react"
import { fetchPing } from "@/lib/api"
import type { PingResponse } from "@/lib/api"

const POLL_MS = 10_000

export function usePing() {
  const [ping, setPing] = useState<PingResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const tick = () => {
      fetchPing()
        .then((res) => {
          if (cancelled) return
          setPing(res)
          setError(null)
        })
        .catch((err) => {
          if (cancelled) return
          setError(err instanceof Error ? err.message : String(err))
          setPing(null)
        })
    }

    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  // `ok` only when the agent is fully booted - needs_auth is reachable but
  // not actually ready to run anything, so callers gating the Run button on
  // this flag should remain disabled until the OAuth flow completes.
  const ok = !!ping && ping.status === "healthy" && !error
  return { ping, error, ok }
}
