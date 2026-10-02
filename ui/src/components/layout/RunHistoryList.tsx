import { useState } from "react"
import {
  CheckCircle2,
  Coins,
  History,
  Pencil,
  Play,
  Trash2,
  XCircle,
  Wrench,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { formatTokens, relativeTime } from "@/lib/format"
import type { RunSummary } from "@/lib/api"
import { SidebarSection } from "@/components/layout/SidebarSection"
import { CountPill } from "@/components/shared/count-pill"
import { EmptyState } from "@/components/shared/empty-state"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"

interface RunHistoryListProps {
  runs: RunSummary[]
  activeRunId: string | null
  onReplay: (run: RunSummary) => void
  onDelete: (id: string) => void
  onRename: (id: string, name: string | null) => void
  disabled?: boolean
}

function StatusIcon({ status }: { status: RunSummary["status"] }) {
  switch (status) {
    case "running":
      return <Spinner className="size-3 shrink-0 text-muted-foreground" />
    case "done":
      return <CheckCircle2 className="size-3 shrink-0 text-success" />
    case "error":
    case "cancelled":
      return <XCircle className="size-3 shrink-0 text-destructive" />
  }
}

export function RunHistoryList({
  runs,
  activeRunId,
  onReplay,
  onDelete,
  onRename,
  disabled = false,
}: RunHistoryListProps) {
  return (
    <SidebarSection
      label="History"
      icon={<History className="size-3.5 shrink-0" />}
      meta={runs.length > 0 ? <CountPill>{runs.length}</CountPill> : undefined}
      defaultOpen={false}
    >
      {runs.length === 0 ? (
        <EmptyState title="No past runs yet." />
      ) : (
        <ul className="space-y-1">
          {runs.map((run) => (
            <RunHistoryRow
              key={run.id}
              run={run}
              active={run.id === activeRunId}
              onReplay={onReplay}
              onDelete={onDelete}
              onRename={onRename}
              disabled={disabled}
            />
          ))}
        </ul>
      )}
    </SidebarSection>
  )
}

interface RunHistoryRowProps {
  run: RunSummary
  active: boolean
  onReplay: (run: RunSummary) => void
  onDelete: (id: string) => void
  onRename: (id: string, name: string | null) => void
  disabled: boolean
}

function RunHistoryRow({
  run,
  active,
  onReplay,
  onDelete,
  onRename,
  disabled,
}: RunHistoryRowProps) {
  const [editing, setEditing] = useState(false)
  // Only shown while editing; startEditing() reseeds it from the current name.
  const [draft, setDraft] = useState(run.name ?? "")

  const displayName = run.name?.trim() || run.incident_id

  const startEditing = (e: React.MouseEvent) => {
    e.stopPropagation()
    setDraft(run.name ?? "")
    setEditing(true)
  }

  const commit = () => {
    if (!editing) return
    const trimmed = draft.trim()
    const next = trimmed.length > 0 ? trimmed : null
    setEditing(false)
    if (next !== (run.name ?? null)) onRename(run.id, next)
  }

  const cancel = () => {
    setDraft(run.name ?? "")
    setEditing(false)
  }

  const handleReplay = () => {
    if (editing) return
    onReplay(run)
  }

  return (
    <li>
      <div
        role="button"
        tabIndex={disabled || editing ? -1 : 0}
        aria-label={`Replay ${displayName}`}
        onClick={handleReplay}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            handleReplay()
          }
        }}
        className={cn(
          "group flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
          editing ? "cursor-default" : "cursor-pointer",
          active
            ? "border-ring/60 bg-sidebar-accent text-sidebar-accent-foreground"
            : "border-transparent hover:bg-sidebar-accent/50",
          disabled && "pointer-events-none opacity-60",
        )}
      >
        <StatusIcon status={run.status} />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-1.5">
            {editing ? (
              <Input
                type="text"
                autoFocus
                value={draft}
                placeholder={run.incident_id}
                onFocus={(e) => e.currentTarget.select()}
                onChange={(e) => setDraft(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onBlur={commit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    commit()
                  } else if (e.key === "Escape") {
                    e.preventDefault()
                    cancel()
                  }
                }}
                className="h-7 min-w-0 flex-1 px-1.5 text-xs md:text-xs font-medium"
              />
            ) : (
              <span
                className="truncate font-medium"
                title={run.name ? `${run.name} · ${run.incident_id}` : run.incident_id}
              >
                {displayName}
              </span>
            )}
          </div>
          {!editing && (
            <div className="mt-0.5 flex items-center gap-2 text-muted-foreground">
              <span>{relativeTime(run.started_at)}</span>
              {run.tool_call_count > 0 && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center gap-1">
                      <Wrench className="size-2.5" />
                      {run.tool_call_count}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    {run.tool_call_count} tool call
                    {run.tool_call_count === 1 ? "" : "s"}
                  </TooltipContent>
                </Tooltip>
              )}
              {(run.input_tokens > 0 || run.output_tokens > 0) && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center gap-1">
                      <Coins className="size-2.5" />
                      {formatTokens(run.input_tokens + run.output_tokens)}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    {run.input_tokens} in / {run.output_tokens} out
                  </TooltipContent>
                </Tooltip>
              )}
            </div>
          )}
        </div>
        {!editing && (
          <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Rename"
                  className="text-muted-foreground"
                  onClick={startEditing}
                >
                  <Pencil />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Rename</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Replay"
                  className="text-muted-foreground"
                  onClick={(e) => {
                    e.stopPropagation()
                    onReplay(run)
                  }}
                >
                  <Play />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Replay</TooltipContent>
            </Tooltip>
            <AlertDialog>
              <Tooltip>
                <TooltipTrigger asChild>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label="Delete"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Trash2 />
                    </Button>
                  </AlertDialogTrigger>
                </TooltipTrigger>
                <TooltipContent>Delete</TooltipContent>
              </Tooltip>
              <AlertDialogContent size="sm" onClick={(e) => e.stopPropagation()}>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete run?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This permanently removes “{displayName}” and its recorded
                    events from the run history. This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel onClick={(e) => e.stopPropagation()}>
                    Cancel
                  </AlertDialogCancel>
                  <AlertDialogAction
                    variant="destructive"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDelete(run.id)
                    }}
                  >
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </div>
    </li>
  )
}
