import { useEffect, useState } from "react"
import { fetchSkills } from "@/lib/api"
import type { SkillInfo } from "@/lib/api"

export function useSkills() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetchSkills()
      .then((res) => {
        if (!cancelled) setSkills(res.skills)
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

  return { skills, error, loading }
}
