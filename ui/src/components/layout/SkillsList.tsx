import { BookOpen } from "lucide-react"
import { ToggleList } from "@/components/layout/ToggleList"
import type { SkillInfo } from "@/lib/api"

interface SkillsListProps {
  skills: SkillInfo[]
  enabled: Set<string>
  onToggle: (name: string, value: boolean) => void
  disabled?: boolean
}

/**
 * Per-skill on/off switches in the sidebar. The set of enabled names goes
 * out as ``skills=`` on the next ``/run`` request, which the server uses
 * to filter the ``AgentSkills`` plugin attached to the diagnosis sub-agent.
 *
 * Default state in the parent component should be all-on; disabling all
 * removes the ``skills`` tool entirely (a useful A/B for showing the
 * impact of skills on cost and behaviour).
 */
export function SkillsList({
  skills,
  enabled,
  onToggle,
  disabled = false,
}: SkillsListProps) {
  return (
    <ToggleList
      label="Skills"
      icon={<BookOpen className="size-3.5 shrink-0" />}
      emptyTitle="No skills available."
      rows={skills.map((s) => ({
        name: s.name,
        description: s.description || undefined,
      }))}
      enabled={enabled}
      onToggle={onToggle}
      disabled={disabled}
    />
  )
}
