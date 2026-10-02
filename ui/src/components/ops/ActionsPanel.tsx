import { useState } from "react"
import {
  Activity,
  BellRing,
  Bug,
  CheckCheck,
  ClipboardCheck,
  GitMerge,
  Play,
  RotateCcw,
  type LucideIcon,
} from "lucide-react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { OpsAction, OpsActionGroup } from "@/lib/ops"
import { cn } from "@/lib/utils"

const GROUPS: { id: OpsActionGroup; title: string }[] = [
  { id: "live", title: "Full scenario" },
  { id: "steps", title: "Steps" },
  { id: "prepare", title: "Prepare" },
]

// Icons by what an action does (one set of buttons per scenario shares
// them); anything new gets Play.
const ICONS: Record<string, LucideIcon> = {
  live: Activity,
  reset: RotateCcw,
  "pd-resolve": CheckCheck,
  induce: Bug,
  page: BellRing,
  "gh-warmup": GitMerge,
  preflight: ClipboardCheck,
}

interface ActionsPanelProps {
  /** Null until GET /actions answers. */
  actions: OpsAction[] | null
  /** True while a job runs (or one is being started): every button locks. */
  busy: boolean
  onRun: (action: OpsAction) => void
}

/** The make targets as buttons, grouped; the ones that page a human ask first. */
export function ActionsPanel({ actions, busy, onRun }: ActionsPanelProps) {
  // Kept after closing so the dialog's exit animation still shows its text.
  const [confirming, setConfirming] = useState<OpsAction | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const trigger = (action: OpsAction) => {
    if (action.confirm) {
      setConfirming(action)
      setConfirmOpen(true)
    } else {
      onRun(action)
    }
  }

  return (
    <Card className="@container gap-4 py-4">
      <CardHeader className="px-4">
        <CardTitle className="text-sm">Actions</CardTitle>
        <CardDescription className="text-xs">
          {busy ? "A job is running - buttons unlock when it ends." : "One make target at a time."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 px-4">
        {actions === null
          ? GROUPS.map((g) => <Skeleton key={g.id} className="h-16 w-full" />)
          : GROUPS.map((group) => {
              const items = actions.filter((a) => a.group === group.id)
              if (items.length === 0) return null
              return (
                <div key={group.id} className="space-y-2">
                  <h3 className="text-[10px] font-medium tracking-wider text-muted-foreground uppercase">
                    {group.title}
                  </h3>
                  <div className="grid gap-2 @md:grid-cols-2 @3xl:grid-cols-3">
                    {items.map((action) => {
                      const Icon = ICONS[action.kind] ?? Play
                      const live = group.id === "live"
                      return (
                        <Button
                          key={action.name}
                          variant={live ? "default" : "outline"}
                          disabled={busy}
                          onClick={() => trigger(action)}
                          className="h-auto w-full items-start justify-start gap-3 px-3 py-2.5 text-left whitespace-normal"
                        >
                          <Icon className="mt-0.5" />
                          <span className="min-w-0 flex-1">
                            <span className="block font-medium">{action.label}</span>
                            <span
                              className={cn(
                                "mt-0.5 block text-xs font-normal",
                                live ? "text-primary-foreground/70" : "text-muted-foreground",
                              )}
                            >
                              {action.description}
                            </span>
                          </span>
                        </Button>
                      )
                    })}
                  </div>
                </div>
              )
            })}
      </CardContent>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Run “{confirming?.label}”?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p className="font-medium text-foreground">
                  This pages whoever is on call in PagerDuty.
                </p>
                <p>{confirming?.description}</p>
                <p className="font-mono text-xs">$ make {confirming?.name}</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={busy}
              onClick={() => {
                if (confirming) onRun(confirming)
              }}
            >
              <BellRing />
              Run and page
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
