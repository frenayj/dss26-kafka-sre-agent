import { AlertTriangle, BookOpen, ExternalLink } from "lucide-react"
import { Callout } from "@/components/shared/callout"
import { KeyValueList } from "@/components/shared/key-value-list"
import { StatusBadge } from "@/components/shared/status-badge"
import { parseTriage, type TriageKnowledge, type TriageResult } from "@/lib/triage"
import { cn } from "@/lib/utils"
import { severityToTone } from "./kafka/parse"
import { AgeBadge } from "./KbResults"
import { Markdown } from "./Markdown"

function Unknown() {
  return <span className="text-muted-foreground/60">-</span>
}

function KnowledgePage({ page }: { page: TriageKnowledge }) {
  const conflicted = page.conflicts.length > 0
  return (
    <li className={cn("space-y-1.5 px-3 py-2.5", conflicted && "bg-warning/5")}>
      <div className="flex min-w-0 items-center gap-2">
        <BookOpen className={cn("size-3.5 shrink-0", conflicted ? "text-warning" : "text-info")} />
        {page.url ? (
          <a
            href={page.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-w-0 items-center gap-1 text-sm font-medium hover:underline"
            title="Open in Confluence"
          >
            <span className="truncate">{page.title}</span>
            <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
          </a>
        ) : (
          <span className="truncate text-sm font-medium">{page.title}</span>
        )}
        <span className="ml-auto flex shrink-0 items-center gap-2">
          {conflicted && (
            <StatusBadge tone="warning">
              {page.conflicts.length} conflict{page.conflicts.length === 1 ? "" : "s"}
            </StatusBadge>
          )}
          <AgeBadge date={page.lastReviewed} />
        </span>
      </div>
      {page.says && <p className="text-xs text-muted-foreground">{page.says}</p>}
      {conflicted && (
        <ul className="space-y-1">
          {page.conflicts.map((c, i) => (
            <li key={i} className="flex gap-1.5 text-xs">
              <AlertTriangle className="mt-0.5 size-3 shrink-0 text-warning" />
              <span>{c}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

/**
 * Triage's answer to the supervisor: the incident, where it happened, and
 * what the team's knowledge base says about it - with every claim the
 * alert or the cluster contradicts.
 */
export function TriageCard({ triage }: { triage: TriageResult }) {
  const t = triage
  const rows = [
    { key: "Cluster", value: t.cluster },
    // A consumer-lag alert names a group; a connector alert names a connector.
    ...(t.connector && !t.consumerGroup
      ? [{ key: "Connector", value: t.connector }]
      : [{ key: "Consumer group", value: t.consumerGroup }]),
    { key: "Topic", value: t.topic },
    { key: "Downstream topic", value: t.downstreamTopic },
    { key: "Service", value: t.service },
    { key: "Repo", value: t.serviceRepo },
  ].map(({ key, value }) => ({ key, value: value ?? <Unknown /> }))
  const conflicted = t.knowledge.filter((p) => p.conflicts.length > 0).length

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          {t.severity && <StatusBadge tone={severityToTone(t.severity)}>{t.severity}</StatusBadge>}
          {t.incidentId && (
            <span className="font-mono text-xs text-muted-foreground">{t.incidentId}</span>
          )}
        </div>
        {t.title && <div className="text-sm font-medium">{t.title}</div>}
      </div>

      {t.summary && (
        <Callout variant="warning" size="sm" icon={<AlertTriangle className="size-3.5" />}>
          {t.summary}
        </Callout>
      )}

      <KeyValueList rows={rows} />

      {t.knowledge.length > 0 && (
        <section className="space-y-1.5">
          <h4 className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
            Knowledge base
            <span className="font-normal tracking-normal normal-case">
              {t.knowledge.length} page{t.knowledge.length === 1 ? "" : "s"}
              {conflicted > 0 && (
                <span className="text-warning"> · {conflicted} contradicted</span>
              )}
            </span>
          </h4>
          <ul className="divide-y divide-border/60 overflow-hidden rounded-md border border-border/60">
            {t.knowledge.map((page, i) => (
              <KnowledgePage key={page.url ?? i} page={page} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/** ``triage_agent``'s result: the card when it parses, else the text as sent. */
export function TriageSummary({ content }: { content: string }) {
  const triage = parseTriage(content)
  return triage ? <TriageCard triage={triage} /> : <Markdown content={content} />
}
