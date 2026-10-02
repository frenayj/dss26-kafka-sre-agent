import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { ArrowLeft, LayoutDashboard, ServerOff } from "lucide-react"
import { ModeToggle } from "@/components/mode-toggle"
import { ActionsPanel } from "@/components/ops/ActionsPanel"
import { ModelsPanel } from "@/components/ops/ModelsPanel"
import { useNow, useOpsActions, useOpsJob, useOpsStatus } from "@/components/ops/hooks"
import { OutputPanel } from "@/components/ops/OutputPanel"
import { StatusBoard } from "@/components/ops/StatusBoard"
import { StatusDot } from "@/components/shared/status-dot"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Spinner } from "@/components/ui/spinner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { OPS_BASE, startOpsAction, stopOpsJob, type OpsAction } from "@/lib/ops"

// Hidden presenter page at #/ops: live status of everything the demo touches,
// a button per make target (reset, break, page, resolve), run one at a time
// by the host-side console server (`make ops`, harness/ops/ops_server.py),
// and the model each agent runs on (set on the agent server itself).
// Not linked from the UI - navigate by URL.

const OPS_HOST = OPS_BASE.replace(/^https?:\/\//, "")

function ConnectionIndicator({ connected }: { connected: boolean | null }) {
  const [tone, label] =
    connected === null
      ? (["muted", "Connecting…"] as const)
      : connected
        ? (["success", "Connected"] as const)
        : (["destructive", "Unreachable"] as const)
  return (
    <div className="flex items-center gap-2 text-xs" title={`Console server at ${OPS_BASE}`}>
      <StatusDot tone={tone} pulse={connected === true} />
      <span className="font-medium">{label}</span>
      <span className="hidden font-mono text-muted-foreground sm:inline">{OPS_HOST}</span>
    </div>
  )
}

function Unreachable() {
  return (
    <Empty className="min-h-[60vh] border border-dashed">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <ServerOff />
        </EmptyMedia>
        <EmptyTitle>Console server not reachable</EmptyTitle>
        <EmptyDescription>
          Start the console server with{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
            make ops
          </code>
        </EmptyDescription>
      </EmptyHeader>
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Spinner className="size-3" />
        Retrying {OPS_HOST} every few seconds
      </p>
    </Empty>
  )
}

export default function OpsPage() {
  const now = useNow()
  const { status, connected, lagHistory } = useOpsStatus()
  const actions = useOpsActions()
  const { job, lines, refresh } = useOpsJob()
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)

  // Re-read the job as soon as the server is back: it may have restarted
  // (no job) while the slower idle poll was waiting.
  useEffect(() => {
    if (connected) refresh()
  }, [connected, refresh])

  const run = useCallback(
    async (action: OpsAction) => {
      setStarting(true)
      try {
        await startOpsAction(action.name)
      } catch (err) {
        toast.error(`Could not start “${action.label}”`, {
          description: err instanceof Error ? err.message : String(err),
        })
      } finally {
        setStarting(false)
        // Pick up the new job (or the one that blocked us) right away.
        refresh()
      }
    },
    [refresh],
  )

  const stop = useCallback(async () => {
    setStopping(true)
    try {
      if (!(await stopOpsJob())) toast.info("The job had already finished")
    } catch (err) {
      toast.error("Could not stop the job", {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setStopping(false)
      refresh()
    }
  }, [refresh])

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-screen bg-background text-foreground">
        <header className="sticky top-0 z-10 flex items-center gap-3 border-b bg-background/95 px-4 py-2.5 backdrop-blur">
          <Button variant="ghost" size="icon-sm" asChild>
            <a href="#/" aria-label="Back to dashboard">
              <ArrowLeft className="size-4" />
            </a>
          </Button>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold">Operator console</h1>
            <p className="hidden truncate text-xs text-muted-foreground sm:block">
              Live demo status and scenario controls
            </p>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <ConnectionIndicator connected={connected} />
            <Button variant="outline" size="sm" asChild>
              <a href="#/">
                <LayoutDashboard />
                <span className="hidden sm:inline">Dashboard</span>
              </a>
            </Button>
            <ModeToggle />
          </div>
        </header>

        <main className="mx-auto max-w-[1600px] space-y-4 p-4 md:p-6">
          {connected === false ? (
            <Unreachable />
          ) : connected === null ? (
            <div className="flex min-h-[60vh] items-center justify-center gap-2 text-sm text-muted-foreground">
              <Spinner />
              Connecting to {OPS_HOST}…
            </div>
          ) : (
            <>
              <StatusBoard status={status} lagHistory={lagHistory} now={now} />
              <div className="grid gap-4 xl:grid-cols-[minmax(0,30rem)_minmax(0,1fr)]">
                <div className="space-y-4">
                  <ActionsPanel
                    actions={actions}
                    busy={starting || job?.status === "running"}
                    onRun={run}
                  />
                  <ModelsPanel />
                </div>
                <OutputPanel
                  job={job}
                  lines={lines}
                  now={now}
                  stopping={stopping}
                  onStop={stop}
                />
              </div>
            </>
          )}
        </main>
      </div>
    </TooltipProvider>
  )
}
