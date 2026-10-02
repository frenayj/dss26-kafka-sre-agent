import { memo, useLayoutEffect, useRef, useState } from "react"
import { ArrowDown, Square, SquareTerminal } from "lucide-react"
import { StatusBadge } from "@/components/shared/status-badge"
import type { Tone } from "@/components/shared/tone"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { formatDuration, type OpsJob, type OpsJobStatus } from "@/lib/ops"
import { cn } from "@/lib/utils"

const STATUS_TONE: Record<OpsJobStatus, Tone> = {
  running: "info",
  succeeded: "success",
  failed: "destructive",
  stopped: "warning",
}

/** Within this many px of the bottom counts as "following" the output. */
const STICK_PX = 24

// The terminal is dark in both themes, so line colours are fixed rather than
// theme tokens (the light-theme tokens are too dark to read on it).
function lineClass(line: string): string | undefined {
  const github = line.includes("github>") && "bg-sky-400/8 text-sky-100"
  if (/ERROR|FAIL|^make: \*\*\*|^\[exit [1-9]/.test(line)) return cn(github, "text-red-400")
  if (line.includes("WARN")) return cn(github, "text-amber-300")
  if (line.includes("[ok]") || line === "[exit 0]") return cn(github, "text-emerald-400")
  if (line.startsWith("$ make ")) return "text-neutral-500"
  return github || undefined
}

/** The scrolling line list. Memoised: the panel re-renders every second for
 *  the elapsed timer, the lines only change when output arrives. Follows the
 *  bottom unless the user has scrolled up. */
const OutputLines = memo(function OutputLines({ lines }: { lines: string[] }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [following, setFollowing] = useState(true)

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && following) el.scrollTop = el.scrollHeight
  }, [lines, following])

  return (
    <div className="relative min-h-[24rem] flex-1">
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget
          setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX)
        }}
        className="mac-scrollbar absolute inset-0 overflow-auto rounded-lg border border-neutral-800 bg-neutral-950 py-3 font-mono text-xs leading-relaxed text-neutral-300"
        role="log"
      >
        {lines.map((line, i) => (
          <div key={i} className={cn("px-3 break-words whitespace-pre-wrap", lineClass(line))}>
            {line || " "}
          </div>
        ))}
      </div>
      {!following && (
        <Button
          size="xs"
          variant="secondary"
          className="absolute right-4 bottom-3 shadow-sm"
          onClick={() => setFollowing(true)}
        >
          <ArrowDown />
          Latest
        </Button>
      )}
    </div>
  )
})

interface OutputPanelProps {
  job: OpsJob | null
  lines: string[]
  now: number
  stopping: boolean
  onStop: () => void
}

/** The current or last job: label, status, elapsed time and its output. */
export function OutputPanel({ job, lines, now, stopping, onStop }: OutputPanelProps) {
  const running = job?.status === "running"
  return (
    <Card className="min-w-0 gap-3 py-4">
      <CardHeader className="flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1 px-4">
        <SquareTerminal className="size-4 shrink-0 text-muted-foreground" />
        <CardTitle className="text-sm">Output</CardTitle>
        {job && (
          <>
            <span className="min-w-0 truncate text-sm font-medium">{job.label}</span>
            <StatusBadge tone={STATUS_TONE[job.status]} className="gap-1">
              {running && <Spinner className="size-2.5" />}
              {job.status}
              {job.status === "failed" && job.exit_code !== null && ` (${job.exit_code})`}
            </StatusBadge>
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {formatDuration((job.ended_at ?? now) - job.started_at)}
            </span>
            {running && (
              <Button
                variant="outline"
                size="xs"
                className="ml-auto"
                disabled={stopping}
                onClick={onStop}
              >
                {stopping ? <Spinner /> : <Square />}
                Stop
              </Button>
            )}
          </>
        )}
      </CardHeader>
      <CardContent className="flex flex-1 flex-col px-4">
        {job ? (
          <OutputLines key={`${job.id}:${job.started_at}`} lines={lines} />
        ) : (
          <div className="flex min-h-[24rem] flex-1 items-center justify-center rounded-lg border border-neutral-800 bg-neutral-950 font-mono text-xs text-neutral-500">
            No job has run yet. Pick an action to see its output here.
          </div>
        )}
      </CardContent>
    </Card>
  )
}
