import { useEffect, useState } from "react"
import { fetchMcpServers } from "@/lib/api"
import type { McpServerInfo } from "@/lib/api"

export function useMcpServers() {
  const [servers, setServers] = useState<McpServerInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetchMcpServers()
      .then((res) => {
        if (!cancelled) setServers(res.servers)
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

  return { servers, error, loading }
}
