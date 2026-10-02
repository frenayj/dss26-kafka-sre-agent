import { useState } from "react"
import { BookOpen, ExternalLink, Calendar, Maximize2, X } from "lucide-react"
import { JsonView } from "./JsonView"
import { Markdown } from "./Markdown"
import { Expander } from "@/components/shared/expander"
import { Button } from "@/components/ui/button"
import { safeParseJson } from "@/lib/format"
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"

interface CreatePageResultProps {
  input: unknown
  content: string
}

interface CreatePageShape {
  id?: string
  url?: string
  space?: string
  title?: string
  created_at?: string
}

function parse(content: string): CreatePageShape | null {
  try {
    return JSON.parse(content) as CreatePageShape
  } catch {
    return null
  }
}

function parseBody(input: unknown): string | null {
  if (input == null) return null
  const obj =
    typeof input === "string" ? safeParseJson(input) : (input as Record<string, unknown>)
  if (!obj || typeof obj !== "object") return null
  return typeof obj.body === "string" ? obj.body : null
}

export function CreatePageResult({ input, content }: CreatePageResultProps) {
  const [docOpen, setDocOpen] = useState(false)
  const page = parse(content)
  const body = parseBody(input)

  if (!page) return <JsonView content={content} />

  return (
    <div className="space-y-2">
      <div className="rounded border border-info/40 bg-card/60 p-3 space-y-2">
        <div className="flex items-center gap-2">
          <BookOpen className="size-4 text-info shrink-0" />
          <span className="text-sm font-medium truncate">{page.title || "Confluence page"}</span>
          {page.space && (
            <span className="text-xs text-muted-foreground font-mono">in {page.space}</span>
          )}
          {body && (
            <button
              type="button"
              onClick={() => setDocOpen(true)}
              className="ml-auto inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-info hover:bg-info/10 hover:text-info/90 transition-colors shrink-0"
              title="Open full document view"
            >
              <Maximize2 className="size-3" />
              Open document
            </button>
          )}
        </div>
        {page.url && (
          <a
            href={page.url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-xs text-info hover:underline font-mono truncate"
          >
            <span className="truncate">{page.url}</span>
            <ExternalLink className="size-3 shrink-0" />
          </a>
        )}
        {page.created_at && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Calendar className="size-3" />
            {page.created_at}
          </div>
        )}
      </div>
      {body && (
        <Expander
          label={`View page body (${body.length.toLocaleString()} chars)`}
          triggerClassName="normal-case tracking-normal"
        >
          <div className="bg-muted/40 rounded p-3 max-h-[24rem] overflow-auto mac-scrollbar text-xs">
            <Markdown content={body} />
          </div>
        </Expander>
      )}

      {body && (
        <Dialog open={docOpen} onOpenChange={setDocOpen}>
          <DialogContent
            className="!max-w-[min(900px,calc(100vw-2rem))] w-full h-[calc(100vh-4rem)] !top-[2rem] !translate-y-0 p-0 bg-gray-100 border-gray-300 overflow-hidden flex flex-col"
            showCloseButton={false}
          >
            <DialogTitle className="sr-only">
              {page.title || "Confluence page"}
            </DialogTitle>
            <DialogDescription className="sr-only">
              Full document view of the generated RCA page body
            </DialogDescription>

            <div className="flex items-center gap-3 px-5 py-2.5 border-b border-gray-300 bg-white shrink-0">
              <BookOpen className="size-4 text-gray-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-900 truncate">
                  {page.title || "Confluence page"}
                </div>
                {page.space && (
                  <div className="text-xs text-gray-500 font-mono">
                    {page.space}{page.created_at ? ` · ${page.created_at}` : ""}
                  </div>
                )}
              </div>
              {page.url && (
                <a
                  href={page.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-700 hover:underline font-mono shrink-0"
                >
                  Open in Confluence
                  <ExternalLink className="size-3" />
                </a>
              )}
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => setDocOpen(false)}
                className="ml-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900"
                title="Close (Esc)"
              >
                <X className="size-4" />
                <span className="sr-only">Close</span>
              </Button>
            </div>

            <div className="flex-1 overflow-y-auto bg-gray-100">
              <article className="mx-auto my-8 max-w-3xl bg-white shadow-md rounded-sm px-12 py-14 sm:px-16 sm:py-16">
                <Markdown content={body} variant="document" />
              </article>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
