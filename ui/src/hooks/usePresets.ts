import { useEffect, useState } from "react"
import { fetchPresets } from "@/lib/api"

export function usePresets() {
  const [presets, setPresets] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetchPresets()
      .then((res) => {
        if (!cancelled) setPresets(res.presets)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { presets, error, loading }
}
