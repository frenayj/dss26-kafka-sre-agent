import { BookOpen, MessageSquare, ExternalLink } from "lucide-react"
import { MarkdownPanel } from "@/components/shared/markdown-panel"

interface ReporterResultProps {
  content: string
}

const CONFLUENCE_RE = /https?:\/\/[^\s)]+confluence[^\s)]*/i
const SLACK_CHANNEL_RE = /#([a-z0-9_-]+)/i

export function ReporterResult({ content }: ReporterResultProps) {
  const confluenceUrl = content.match(CONFLUENCE_RE)?.[0] ?? null
  const slackChannel = content.match(SLACK_CHANNEL_RE)?.[1] ?? null

  return (
    <div className="space-y-2">
      {(confluenceUrl || slackChannel) && (
        <div className="rounded border border-border/50 bg-card/60 p-3 space-y-2">
          {confluenceUrl && (
            <a
              href={confluenceUrl}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 text-sm text-info hover:underline"
            >
              <BookOpen className="size-4 shrink-0" />
              <span className="truncate font-mono">{confluenceUrl}</span>
              <ExternalLink className="size-3 shrink-0" />
            </a>
          )}
          {slackChannel && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <MessageSquare className="size-4 shrink-0" />
              Posted to <span className="font-mono">#{slackChannel}</span>
            </div>
          )}
        </div>
      )}
      <MarkdownPanel content={content} maxHClassName="max-h-[24rem]" />
    </div>
  )
}
