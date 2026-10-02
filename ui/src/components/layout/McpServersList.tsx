import { Server } from "lucide-react"
import { ToggleList } from "@/components/layout/ToggleList"
import type { McpServerInfo } from "@/lib/api"

interface McpServersListProps {
  servers: McpServerInfo[]
  enabled: Set<string>
  onToggle: (name: string, value: boolean) => void
  disabled?: boolean
}

/**
 * Per-MCP-server on/off switches in the sidebar. Mirrors :component:`SkillsList`
 * - same layout, same precedence rule (omitted param = all enabled,
 * empty list = none).
 *
 * Each row also surfaces which sub-agent depends on the server, so the
 * user can predict the impact of flipping a switch off ("disabling
 * GitHub blinds the forensics sub-agent").
 */
export function McpServersList({
  servers,
  enabled,
  onToggle,
  disabled = false,
}: McpServersListProps) {
  return (
    <ToggleList
      label="MCP servers"
      icon={<Server className="size-3.5 shrink-0" />}
      emptyTitle="No MCP servers available."
      rows={servers.map((s) => ({
        name: s.name,
        label: (
          <>
            <span className="truncate font-mono">{s.name}</span>
            <span className="shrink-0 text-[10px] tracking-wider text-muted-foreground/80 uppercase">
              → {s.sub_agent}
            </span>
          </>
        ),
        meta: s.tool_count > 0 ? `${s.tool_count} tools` : undefined,
        description: s.description || undefined,
      }))}
      enabled={enabled}
      onToggle={onToggle}
      disabled={disabled}
    />
  )
}
