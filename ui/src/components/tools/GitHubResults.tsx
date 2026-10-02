import {
  CheckCircle2,
  FileCode,
  FileDiff,
  Folder,
  GitCommit,
  GitMerge,
  GitPullRequest,
  MinusCircle,
  Search,
  User,
  XCircle,
} from "lucide-react"
import { StatusBadge } from "@/components/shared/status-badge"
import { CodeBlock } from "@/components/shared/code-block"
import { safeParseJson } from "@/lib/format"
import { DiffView } from "./DiffView"
import { JsonView } from "./JsonView"

/*
 * Renderers for GitHub's official MCP server tools (github/github-mcp-server).
 * The offline stub serves the same tool names and shapes, so these cover both
 * GITHUB_MODE=live and GITHUB_MODE=stub. Every renderer falls back to the raw
 * JSON when a payload doesn't match - an error string or an unexpected shape
 * must still be readable.
 */

type Json = Record<string, unknown>

function parseAny(content: string): unknown {
  try {
    return JSON.parse(content)
  } catch {
    return null
  }
}

function parseInput(input: unknown): Json {
  if (input == null) return {}
  if (typeof input === "string") return safeParseJson(input) ?? {}
  return typeof input === "object" ? (input as Json) : {}
}

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined
}

function shortDate(iso: string | undefined): string | undefined {
  return iso ? iso.replace("T", " ").replace(/:\d\dZ$/, "Z") : undefined
}

function repoFromUrl(url: string | undefined): string | undefined {
  const m = url?.match(/github\.com\/([^/]+\/[^/]+)\//) ?? url?.match(/repos\/([^/]+\/[^/]+)/)
  return m ? m[1] : undefined
}

// ---------------------------------------------------------------------------
// Pull request lists: search_pull_requests + list_pull_requests
// ---------------------------------------------------------------------------

interface PrRow {
  repo?: string
  number: number
  title: string
  user?: string
  state?: string
  mergedAt?: string
  labels: string[]
}

function toPrRow(raw: Json): PrRow {
  const pr = (raw.pull_request as Json | undefined) ?? {}
  const user = raw.user as Json | undefined
  const labels = Array.isArray(raw.labels)
    ? (raw.labels as unknown[]).map((l) => (typeof l === "string" ? l : str((l as Json)?.name) ?? ""))
    : []
  return {
    repo: repoFromUrl(str(raw.html_url) ?? str(raw.repository_url)),
    number: Number(raw.number),
    title: str(raw.title) ?? "",
    user: str(user?.login),
    state: str(raw.state),
    mergedAt: str(pr.merged_at) ?? str(raw.merged_at),
    labels: labels.filter(Boolean),
  }
}

export function GitHubPrListResult({ content }: { content: string }) {
  const parsed = parseAny(content)
  const items: unknown =
    Array.isArray(parsed) ? parsed : (parsed as Json | null)?.items
  if (!Array.isArray(items)) return <JsonView content={content} />
  const rows = (items as Json[]).map(toPrRow)
  const total = !Array.isArray(parsed) ? Number((parsed as Json).total_count ?? rows.length) : rows.length

  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">
        {total} pull request{total === 1 ? "" : "s"}
        {rows.length < total ? ` (showing ${rows.length})` : ""}
      </div>
      <ul className="space-y-1.5">
        {rows.map((pr) => (
          <li
            key={`${pr.repo}#${pr.number}`}
            className="rounded-md border border-border/60 bg-card p-2.5 space-y-1.5"
          >
            <div className="flex items-center gap-2 min-w-0">
              {pr.mergedAt ? (
                <GitMerge className="size-3.5 text-muted-foreground shrink-0" />
              ) : (
                <GitPullRequest className="size-3.5 text-muted-foreground shrink-0" />
              )}
              <span className="font-mono text-xs text-warning shrink-0">#{pr.number}</span>
              <span className="text-sm truncate">{pr.title}</span>
              <StatusBadge
                tone={pr.mergedAt ? "success" : pr.state === "open" ? "info" : "muted"}
                className="ml-auto shrink-0"
              >
                {pr.mergedAt ? "merged" : pr.state ?? "?"}
              </StatusBadge>
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {pr.repo && <span className="font-mono">{pr.repo}</span>}
              {pr.user && (
                <span className="inline-flex items-center gap-1">
                  <User className="size-3" />
                  {pr.user}
                </span>
              )}
              {pr.mergedAt && <span>merged {shortDate(pr.mergedAt)}</span>}
              {pr.labels.length > 0 && <span>{pr.labels.join(" · ")}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// pull_request_read - one tool, many methods
// ---------------------------------------------------------------------------

function filesToDiff(files: Json[]): string {
  return files
    .map((f) => {
      const name = str(f.filename) ?? "?"
      return `diff --git a/${name} b/${name}\n--- a/${name}\n+++ b/${name}\n${str(f.patch) ?? ""}`
    })
    .join("\n")
}

function CheckRuns({ data }: { data: Json }) {
  const runs = Array.isArray(data.check_runs) ? (data.check_runs as Json[]) : []
  if (runs.length === 0) return <div className="text-xs text-muted-foreground">No check runs</div>
  return (
    <ul className="space-y-1">
      {runs.map((r) => {
        const conclusion = str(r.conclusion) ?? str(r.status) ?? "?"
        const Icon =
          conclusion === "success" ? CheckCircle2 : conclusion === "skipped" ? MinusCircle : XCircle
        const tone =
          conclusion === "success" ? "success" : conclusion === "skipped" ? "warning" : "destructive"
        return (
          <li key={String(r.id ?? r.name)} className="flex items-center gap-2 text-sm">
            <Icon className="size-3.5 text-muted-foreground shrink-0" />
            <span className="font-mono text-xs truncate">{str(r.name)}</span>
            <StatusBadge tone={tone} className="ml-auto shrink-0">
              {conclusion}
            </StatusBadge>
          </li>
        )
      })}
    </ul>
  )
}

function PrDetail({ data }: { data: Json }) {
  const row = toPrRow(data)
  const head = data.head as Json | undefined
  return (
    <div className="rounded-md border border-border/60 bg-card p-2.5 space-y-1.5">
      <div className="flex items-center gap-2 min-w-0">
        <GitPullRequest className="size-3.5 text-muted-foreground shrink-0" />
        <span className="font-mono text-xs text-warning shrink-0">#{row.number}</span>
        <span className="text-sm font-medium truncate">{row.title}</span>
        <StatusBadge tone={data.merged ? "success" : "muted"} className="ml-auto shrink-0">
          {data.merged ? "merged" : row.state ?? "?"}
        </StatusBadge>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {row.user && <span>by {row.user}</span>}
        {str(head?.ref) && <span className="font-mono">{str(head?.ref)}</span>}
        {data.changed_files != null && (
          <span>
            {String(data.changed_files)} files · +{String(data.additions ?? 0)} −{String(data.deletions ?? 0)}
          </span>
        )}
        {str(data.closed_at) && <span>closed {shortDate(str(data.closed_at))}</span>}
      </div>
      {str(data.body) && (
        <CodeBlock maxHClassName="max-h-40" className="font-sans">
          {str(data.body)}
        </CodeBlock>
      )}
    </div>
  )
}

export function GitHubPrReadResult({ input, content }: { input: unknown; content: string }) {
  const args = parseInput(input)
  const method = str(args.method) ?? "get"
  const header = (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <FileDiff className="size-3.5" />
      <span className="font-mono">
        {str(args.owner)}/{str(args.repo)}
      </span>
      {args.pullNumber != null && (
        <span className="font-mono text-warning">#{String(args.pullNumber)}</span>
      )}
      <span>{method}</span>
    </div>
  )

  if (method === "get_diff") {
    return (
      <div className="space-y-2">
        {header}
        <DiffView content={content} />
      </div>
    )
  }
  const parsed = parseAny(content)
  let body: React.ReactNode = <JsonView content={content} />
  if (method === "get_files" && Array.isArray(parsed)) {
    body = <DiffView content={filesToDiff(parsed as Json[])} />
  } else if (method === "get_check_runs" && parsed && typeof parsed === "object") {
    body = <CheckRuns data={parsed as Json} />
  } else if (method === "get" && parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    body = <PrDetail data={parsed as Json} />
  } else if (method === "get_commits" && Array.isArray(parsed)) {
    body = <CommitList commits={parsed as Json[]} />
  }
  return (
    <div className="space-y-2">
      {header}
      {body}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Commits: list_commits + get_commit
// ---------------------------------------------------------------------------

function CommitList({ commits }: { commits: Json[] }) {
  return (
    <ul className="space-y-1">
      {commits.map((c) => {
        const inner = (c.commit as Json | undefined) ?? c
        const author = (inner.author as Json | undefined) ?? {}
        const message = str(inner.message) ?? ""
        const sha = str(c.sha) ?? ""
        return (
          <li key={sha} className="flex items-start gap-2 text-sm min-w-0">
            <GitCommit className="size-3.5 mt-0.5 text-muted-foreground shrink-0" />
            <span className="font-mono text-xs text-warning shrink-0">{sha.slice(0, 7)}</span>
            <span className="truncate">{message.split("\n")[0]}</span>
            <span className="ml-auto shrink-0 text-xs text-muted-foreground">
              {str(author.name)} · {shortDate(str(author.date))}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

export function GitHubCommitsResult({ content }: { content: string }) {
  const parsed = parseAny(content)
  if (!Array.isArray(parsed)) return <JsonView content={content} />
  return <CommitList commits={parsed as Json[]} />
}

export function GitHubCommitResult({ content }: { content: string }) {
  const parsed = parseAny(content) as Json | null
  if (!parsed || typeof parsed !== "object" || !parsed.sha) return <JsonView content={content} />
  const files = Array.isArray(parsed.files) ? (parsed.files as Json[]) : []
  const withPatch = files.some((f) => typeof f.patch === "string")
  return (
    <div className="space-y-2">
      <CommitList commits={[parsed]} />
      {withPatch ? (
        <DiffView content={filesToDiff(files)} />
      ) : (
        files.length > 0 && (
          <ul className="space-y-0.5 text-xs font-mono text-muted-foreground">
            {files.map((f) => (
              <li key={str(f.filename)}>
                {str(f.filename)} (+{String(f.additions ?? 0)} −{String(f.deletions ?? 0)})
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Code, files and repos
// ---------------------------------------------------------------------------

export function GitHubCodeSearchResult({ content }: { content: string }) {
  const parsed = parseAny(content) as Json | null
  const items = parsed && Array.isArray(parsed.items) ? (parsed.items as Json[]) : null
  if (!items) return <JsonView content={content} />
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Search className="size-3" />
        {String(parsed?.total_count ?? items.length)} file(s)
      </div>
      <ul className="space-y-1.5">
        {items.map((it) => {
          const matches = Array.isArray(it.text_matches) ? (it.text_matches as Json[]) : []
          return (
            <li key={`${str(it.repository)}:${str(it.path)}`} className="space-y-1">
              <div className="flex items-center gap-2 text-xs min-w-0">
                <FileCode className="size-3 text-muted-foreground shrink-0" />
                <span className="font-mono text-muted-foreground shrink-0">{str(it.repository)}</span>
                <span className="font-mono truncate">{str(it.path)}</span>
              </div>
              {str(matches[0]?.fragment) && (
                <CodeBlock maxHClassName="max-h-28">{str(matches[0]?.fragment)}</CodeBlock>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const DOWNLOADED = /^successfully downloaded (?:text|binary) file \(SHA: [0-9a-f]*\)\s*/

export function GitHubFileResult({ input, content }: { input: unknown; content: string }) {
  const args = parseInput(input)
  const parsed = parseAny(content)
  const where = `${str(args.owner) ?? ""}/${str(args.repo) ?? ""}/${str(args.path) ?? ""}`
  if (Array.isArray(parsed)) {
    return (
      <div className="space-y-1">
        <div className="text-xs font-mono text-muted-foreground">{where}</div>
        <ul className="space-y-0.5">
          {(parsed as Json[]).map((e) => (
            <li key={str(e.path)} className="flex items-center gap-1.5 text-sm font-mono">
              {e.type === "dir" ? (
                <Folder className="size-3.5 text-muted-foreground" />
              ) : (
                <FileCode className="size-3.5 text-muted-foreground" />
              )}
              {str(e.name)}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <div className="space-y-1">
      <div className="text-xs font-mono text-muted-foreground">{where}</div>
      <CodeBlock maxHClassName="max-h-80">{content.replace(DOWNLOADED, "")}</CodeBlock>
    </div>
  )
}

export function GitHubRepoSearchResult({ content }: { content: string }) {
  const parsed = parseAny(content) as Json | null
  const items = parsed && Array.isArray(parsed.items) ? (parsed.items as Json[]) : null
  if (!items) return <JsonView content={content} />
  return (
    <ul className="space-y-1.5">
      {items.map((r) => (
        <li key={str(r.full_name)} className="space-y-0.5">
          <div className="text-sm font-mono">{str(r.full_name)}</div>
          {str(r.description) && (
            <div className="text-xs text-muted-foreground">{str(r.description)}</div>
          )}
          {Array.isArray(r.topics) && r.topics.length > 0 && (
            <div className="text-[11px] text-muted-foreground">{(r.topics as string[]).join(" · ")}</div>
          )}
        </li>
      ))}
    </ul>
  )
}
