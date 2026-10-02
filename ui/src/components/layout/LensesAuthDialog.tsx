import { ExternalLink, ShieldAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"

interface LensesAuthDialogProps {
  authUrl: string | null
}

/**
 * Shown when the FastAPI server is still inside its lifespan startup and the
 * Lenses MCP client is blocked on OAuth. The temporary localhost handler in
 * agent/lenses_oauth.py serves /ping with `{status: "needs_auth", auth_url}`
 * while it waits for the redirect - this dialog turns that signal into an
 * actionable prompt instead of a bare red "agent offline" dot.
 *
 * The dialog has no close affordance: there is no meaningful "cancel" while
 * the agent is genuinely blocked. It auto-dismisses on the next /ping poll
 * once status flips to "healthy".
 */
export function LensesAuthDialog({ authUrl }: LensesAuthDialogProps) {
  const open = authUrl !== null
  return (
    <Dialog open={open}>
      <DialogContent
        showCloseButton={false}
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        className="sm:max-w-md"
      >
        <div className="flex items-start gap-3">
          <div className="rounded-full bg-warning/15 p-2 shrink-0">
            <ShieldAlert className="size-5 text-warning" />
          </div>
          <div className="space-y-1 min-w-0">
            <DialogTitle>Sign in to Lenses MCP</DialogTitle>
            <DialogDescription>
              The agent needs OAuth credentials from Lenses HQ before it can
              run Kafka diagnostics. Sign in to continue.
            </DialogDescription>
          </div>
        </div>

        <div className="mt-2 space-y-3">
          <Button asChild className="w-full">
            <a href={authUrl ?? "#"} target="_blank" rel="noreferrer">
              Open authorization page
              <ExternalLink className="size-4" />
            </a>
          </Button>

          <div className="text-xs text-muted-foreground">
            You'll be redirected back automatically and this dialog will
            close on its own.
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
