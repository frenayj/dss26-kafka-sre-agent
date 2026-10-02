import { useId } from "react"
import { SidebarSection } from "@/components/layout/SidebarSection"
import { CountPill } from "@/components/shared/count-pill"
import { EmptyState } from "@/components/shared/empty-state"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

export interface ToggleListRow {
  /** Stable identity; the string handed back through `onToggle`. */
  name: string
  /** Label-line content. Defaults to a truncated mono render of `name`. */
  label?: React.ReactNode
  /** Right-aligned meta on the label line (e.g. "12 tools"). */
  meta?: React.ReactNode
  /** Secondary line, clamped to two lines. */
  description?: React.ReactNode
}

interface ToggleListProps {
  /** Section header label. */
  label: string
  /** Section header icon. */
  icon?: React.ReactNode
  rows: ToggleListRow[]
  /** Names currently switched on. */
  enabled: Set<string>
  onToggle: (name: string, value: boolean) => void
  disabled?: boolean
  /** EmptyState title shown when `rows` is empty. */
  emptyTitle: React.ReactNode
}

/**
 * Collapsible sidebar section of on/off switch rows. Shared chassis behind
 * :component:`McpServersList` and :component:`SkillsList`: a
 * :component:`SidebarSection` header with an enabled/total CountPill, plus
 * one bordered card row per item (Switch + Label + optional description and
 * right meta).
 */
export function ToggleList({
  label,
  icon,
  rows,
  enabled,
  onToggle,
  disabled = false,
  emptyTitle,
}: ToggleListProps) {
  const uid = useId()
  const onCount = rows.filter((r) => enabled.has(r.name)).length

  return (
    <SidebarSection
      label={label}
      icon={icon}
      defaultOpen={false}
      meta={
        rows.length > 0 ? (
          <CountPill>
            {onCount}/{rows.length}
          </CountPill>
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <EmptyState title={emptyTitle} />
      ) : (
        <ul className="space-y-1.5">
          {rows.map((row, i) => {
            const id = `${uid}-${i}`
            const isOn = enabled.has(row.name)
            return (
              <li
                key={row.name}
                className={cn(
                  "flex items-start gap-2 rounded border border-border/50 bg-card/40 px-2 py-2",
                  disabled && "pointer-events-none opacity-60",
                )}
              >
                <Switch
                  id={id}
                  size="sm"
                  checked={isOn}
                  onCheckedChange={(v) => onToggle(row.name, v)}
                  disabled={disabled}
                  className="mt-0.5 shrink-0"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-1.5">
                    <Label
                      htmlFor={id}
                      className={cn(
                        "min-w-0 flex-1 items-baseline gap-1.5 text-xs font-normal",
                        isOn ? "text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {row.label ?? (
                        <span className="truncate font-mono">{row.name}</span>
                      )}
                    </Label>
                    {row.meta != null && (
                      <span className="shrink-0 font-mono text-[10px] text-muted-foreground/70 tabular-nums">
                        {row.meta}
                      </span>
                    )}
                  </div>
                  {row.description != null && (
                    <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
                      {row.description}
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </SidebarSection>
  )
}
