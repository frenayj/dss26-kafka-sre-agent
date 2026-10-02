import { GitPullRequest, User, Calendar } from "lucide-react"
import { MarkdownPanel } from "@/components/shared/markdown-panel"

interface ForensicsPrProps {
  content: string
}

/**
 * Try to lift a PR number / title / author out of the forensics output so we
 * can render a header strip above the prose. Falls back to plain markdown if
 * nothing matches.
 */
interface ParsedPr {
  number: string | null
  title: string | null
  author: string | null
  mergedAt: string | null
}

function parse(content: string): ParsedPr {
  const numberMatch = content.match(/PR\s*#?(\d{2,6})/i)
  const titleMatch = content.match(/(?:title|PR\s*title)\s*[:=]\s*["']?(.+?)["']?(?:\n|$)/i)
  const authorMatch = content.match(/(?:author|by)\s*[:=]\s*["']?([^"\n,;]+)/i)
  const mergedMatch = content.match(/merged(?:-at|_at|\s+at)?\s*[:=]\s*([0-9T:\-Z .+]+)/i)
  return {
    number: numberMatch ? numberMatch[1] : null,
    title: titleMatch ? titleMatch[1].trim() : null,
    author: authorMatch ? authorMatch[1].trim() : null,
    mergedAt: mergedMatch ? mergedMatch[1].trim() : null,
  }
}

export function ForensicsPr({ content }: ForensicsPrProps) {
  const pr = parse(content)
  const hasAnything = pr.number || pr.title || pr.author

  return (
    <div className="space-y-2">
      {hasAnything && (
        <div className="rounded border border-border/50 bg-card/60 p-3 space-y-1.5">
          <div className="flex items-center gap-2">
            <GitPullRequest className="size-4 text-muted-foreground shrink-0" />
            {pr.number && (
              <span className="font-mono text-sm text-warning">#{pr.number}</span>
            )}
            {pr.title && <span className="text-sm font-medium truncate">{pr.title}</span>}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {pr.author && (
              <span className="inline-flex items-center gap-1">
                <User className="size-3" />
                {pr.author}
              </span>
            )}
            {pr.mergedAt && (
              <span className="inline-flex items-center gap-1">
                <Calendar className="size-3" />
                {pr.mergedAt}
              </span>
            )}
          </div>
        </div>
      )}
      <MarkdownPanel content={content} maxHClassName="max-h-[28rem]" />
    </div>
  )
}
