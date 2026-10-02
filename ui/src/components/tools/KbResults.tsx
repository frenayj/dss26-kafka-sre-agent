import { useState } from "react"
import { BookOpen, ExternalLink, FileText } from "lucide-react"
import { StatusBadge } from "@/components/shared/status-badge"
import { safeParseJson } from "@/lib/format"
import { JsonView } from "./JsonView"
import { Markdown } from "./Markdown"

// Renderers for the Confluence knowledge-base tools (search_pages, get_page).
// Each page carries its age: a runbook last reviewed more than a year ago gets
// a warning badge, so a stale doc stands out before anyone reads it.

const YEAR_MS = 365 * 24 * 60 * 60 * 1000

/** "Last reviewed" in the page body wins over Confluence's edit date. */
const REVIEWED_IN_BODY = /Last reviewed:?\s*\|?\s*(\d{4}-\d{2}-\d{2})/i

/** A page's "Last reviewed" date, flagged once it is a year old or more. */
export function AgeBadge({ date }: { date?: string | null }) {
  // Read the clock once per mount - a year-granularity age never needs to tick.
  const [now] = useState(() => Date.now())
  if (!date) return null
  const t = Date.parse(date)
  if (Number.isNaN(t)) return null
  const years = Math.floor((now - t) / YEAR_MS)
  const day = date.slice(0, 10)
  return years >= 1 ? (
    <StatusBadge tone="warning" className="shrink-0" title={`Last reviewed ${day}`}>
      {years}y old
    </StatusBadge>
  ) : (
    <span className="shrink-0 text-xs text-muted-foreground">{day}</span>
  )
}

interface SearchHit {
  id: string
  title: string
  url?: string | null
  last_modified?: string | null
  excerpt?: string
}

export function KbSearchResult({ content }: { content: string }) {
  const parsed = safeParseJson(content) as { query?: string; results?: SearchHit[] } | null
  if (!parsed || !Array.isArray(parsed.results)) return <JsonView content={content} />
  if (parsed.results.length === 0) {
    return <div className="text-xs text-muted-foreground">No pages match "{parsed.query}".</div>
  }

  return (
    <ul className="space-y-1.5">
      {parsed.results.map((hit) => (
        <li key={hit.id} className="rounded-md border border-border/60 bg-card p-2.5 space-y-1">
          <div className="flex items-center gap-2">
            <FileText className="size-3.5 text-info shrink-0" />
            {hit.url ? (
              <a
                href={hit.url}
                target="_blank"
                rel="noreferrer"
                className="text-sm truncate hover:underline"
              >
                {hit.title}
              </a>
            ) : (
              <span className="text-sm truncate">{hit.title}</span>
            )}
            <span className="ml-auto" />
            <AgeBadge date={hit.last_modified} />
          </div>
          {hit.excerpt && (
            <div className="text-xs text-muted-foreground line-clamp-2">{hit.excerpt}</div>
          )}
        </li>
      ))}
    </ul>
  )
}

interface Page {
  title?: string
  url?: string | null
  last_modified?: string | null
  body?: string
}

export function KbPageResult({ content }: { content: string }) {
  const page = safeParseJson(content) as Page | null
  if (!page || typeof page.body !== "string") return <JsonView content={content} />
  const reviewed = page.body.match(REVIEWED_IN_BODY)?.[1] ?? page.last_modified

  return (
    <div className="rounded border border-info/40 bg-card/60 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <BookOpen className="size-4 text-info shrink-0" />
        <span className="text-sm font-medium truncate">{page.title || "Confluence page"}</span>
        <span className="ml-auto" />
        <AgeBadge date={reviewed} />
        {page.url && (
          <a
            href={page.url}
            target="_blank"
            rel="noreferrer"
            className="text-info hover:text-info/80 shrink-0"
            title="Open in Confluence"
          >
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>
      <div className="bg-muted/40 rounded p-3 max-h-[20rem] overflow-auto mac-scrollbar text-xs">
        <Markdown content={page.body} />
      </div>
    </div>
  )
}
