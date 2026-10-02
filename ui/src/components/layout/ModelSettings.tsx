import { Cpu } from "lucide-react"
import { SidebarSection } from "@/components/layout/SidebarSection"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import type { AgentRole, ModelAlias, ModelSelection } from "@/lib/api"
import { MODELS } from "@/lib/models"

interface ModelRoleListProps {
  /** The server's setting; null until it answers (the selects stay locked). */
  models: ModelSelection | null
  onSelect: (role: AgentRole, alias: ModelAlias) => void
  disabled?: boolean
  className?: string
}

const ROLES: { key: AgentRole; label: string; hint: string }[] = [
  { key: "supervisor", label: "Supervisor", hint: "Incident commander" },
  { key: "triage", label: "Triage", hint: "PagerDuty parser" },
  { key: "diagnosis", label: "Diagnosis", hint: "Lenses MCP + skills" },
  { key: "forensics", label: "Forensics", hint: "GitHub PR hunt" },
  { key: "reporter", label: "Reporter", hint: "Confluence + Slack" },
]

/** A model select per agent role: the dashboard's Models panel and the
 *  operator console's Models card. */
export function ModelRoleList({ models, onSelect, disabled, className }: ModelRoleListProps) {
  const locked = disabled || models === null
  return (
    <div
      className={cn(
        "rounded border border-border/50 bg-card/40 divide-y divide-border/40",
        locked && "opacity-60 pointer-events-none",
        className,
      )}
    >
      {ROLES.map(({ key, label, hint }) => {
        const triggerId = `model-select-${key}`
        return (
          <div key={key} className="flex items-center gap-2 px-2 py-1.5">
            <div className="min-w-0 flex-1">
              <Label
                htmlFor={triggerId}
                className="text-xs font-mono font-normal"
              >
                {label}
              </Label>
              <div className="text-[10px] text-muted-foreground leading-snug">
                {hint}
              </div>
            </div>
            <Select
              value={models?.[key] ?? ""}
              onValueChange={(v) => onSelect(key, v as ModelAlias)}
              disabled={locked}
            >
              <SelectTrigger
                id={triggerId}
                size="sm"
                className="h-7 px-2 text-xs font-mono"
                aria-label={`${label} model`}
              >
                <SelectValue placeholder="…" />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(MODELS) as ModelAlias[]).map((alias) => (
                  <SelectItem
                    key={alias}
                    value={alias}
                    className="text-xs font-mono"
                  >
                    {MODELS[alias].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )
      })}
    </div>
  )
}

export function ModelSettings(props: Omit<ModelRoleListProps, "className">) {
  return (
    <SidebarSection
      label="Models"
      icon={<Cpu className="size-3.5 shrink-0" />}
      defaultOpen={false}
    >
      <ModelRoleList {...props} />
    </SidebarSection>
  )
}
