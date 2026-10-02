import { StatusDot } from "@/components/shared/status-dot"
import type { Tone } from "@/components/shared/tone"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

const HEALTH_LABEL: Record<Tone, string> = {
  success: "Healthy",
  warning: "Needs attention",
  destructive: "Unhealthy",
  info: "Info",
  muted: "Unknown",
  primary: "Info",
}

/** "checked 4s ago" from server timestamps (same host, so no clock skew). */
function checkedAgo(checkedAt: number, now: number): string {
  const sec = Math.max(0, Math.round((now - checkedAt) / 1000))
  if (sec < 60) return `checked ${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `checked ${min}m ago`
  return `checked ${Math.floor(min / 60)}h ago`
}

interface StatusCardProps {
  title: string
  icon: React.ReactNode
  /** The section's check metadata; undefined until its first check lands. */
  section: { error: string | null; checked_at: number } | undefined
  /** Overall health; pass "muted" when it can't be told. */
  tone: Tone
  now: number
  /** Footer link or action, right-aligned. */
  footer?: React.ReactNode
  children?: React.ReactNode
}

/** One status-board card: title + health dot, key facts, the check's error
 *  (if any) and how fresh the check is. */
export function StatusCard({
  title,
  icon,
  section,
  tone,
  now,
  footer,
  children,
}: StatusCardProps) {
  return (
    <Card className="gap-3 py-4">
      <CardHeader className="flex items-center gap-2 px-4">
        <span className="flex size-4 shrink-0 items-center justify-center text-muted-foreground [&_svg]:size-4">
          {icon}
        </span>
        <CardTitle className="min-w-0 flex-1 truncate text-sm">{title}</CardTitle>
        <StatusDot
          tone={tone}
          size="lg"
          role="img"
          aria-label={HEALTH_LABEL[tone]}
          title={HEALTH_LABEL[tone]}
        />
      </CardHeader>
      <CardContent className="flex min-w-0 flex-1 flex-col gap-2 px-4 text-sm">
        {section === undefined ? (
          <p className="text-xs text-muted-foreground">Waiting for the first check…</p>
        ) : (
          children
        )}
        {section?.error && (
          <p
            className="line-clamp-3 font-mono text-[11px] leading-snug break-words text-destructive/80"
            title={section.error}
          >
            {section.error}
          </p>
        )}
      </CardContent>
      <CardFooter className="gap-2 px-4 text-[11px] text-muted-foreground">
        <span className="tabular-nums">
          {section ? checkedAgo(section.checked_at, now) : "not checked yet"}
        </span>
        {footer != null && <span className="ml-auto flex items-center">{footer}</span>}
      </CardFooter>
    </Card>
  )
}
