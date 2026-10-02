import { EmptyState } from "@/components/shared/empty-state"
import { Expander } from "@/components/shared/expander"
import { SectionHeader } from "@/components/shared/section-header"
import { StatusBadge } from "@/components/shared/status-badge"
import { TONE_TEXT, type Tone } from "@/components/shared/tone"
import { cn } from "@/lib/utils"
import { parseArrayToolResult, formatNumber } from "./parse"
import type { TopicDetailData } from "./types"

interface Props {
  result: string
}

/**
 * Compact list view for ``list_topics``. The MCP response includes the same
 * shape as ``get_topic`` per item - full config and partitions - but a list
 * view should be scannable, not exhaustive. We surface only the essentials
 * (name, partitions, replication, total messages, key/value types, badges)
 * and let the user click through to the full detail via a separate
 * ``get_topic`` call.
 */
export function TopicList({ result }: Props) {
  const parsed = parseArrayToolResult<TopicDetailData>(result)
  if (!parsed.ok) return null
  const topics = parsed.data

  // Separate user topics from internal/control topics so the list isn't
  // dominated by __consumer_offsets, __topology, etc.
  const userTopics = topics.filter((t) => !t.isControlTopic && !t.topicName.startsWith("__"))
  const internalTopics = topics.filter(
    (t) => t.isControlTopic || t.topicName.startsWith("__"),
  )

  return (
    <div className="space-y-2.5">
      <SectionHeader
        title="Topics"
        count={topics.length}
        end={
          internalTopics.length > 0 ? (
            <span className="text-[10px] text-muted-foreground">
              {userTopics.length} user · {internalTopics.length} internal
            </span>
          ) : undefined
        }
      />

      {topics.length === 0 ? (
        <EmptyState title="No topics." />
      ) : (
        <>
          {userTopics.length > 0 && (
            <ul className="space-y-1">
              {userTopics.map((t) => (
                <TopicRow key={t.topicName} topic={t} />
              ))}
            </ul>
          )}
          {internalTopics.length > 0 && (
            <Expander label={`Internal topics (${internalTopics.length})`}>
              <ul className="space-y-1">
                {internalTopics.map((t) => (
                  <TopicRow key={t.topicName} topic={t} dim />
                ))}
              </ul>
            </Expander>
          )}
        </>
      )}
    </div>
  )
}

function TopicRow({ topic, dim }: { topic: TopicDetailData; dim?: boolean }) {
  const totalMessages = topic.totalMessages ?? 0
  return (
    <li
      className={cn(
        "flex items-center gap-2 rounded border border-border/50 bg-card/40 px-2.5 py-1.5 text-xs",
        dim && "opacity-70",
      )}
    >
      <span className="min-w-0 flex-1 truncate font-mono font-medium">
        {topic.topicName}
      </span>

      <div className="flex shrink-0 items-center gap-1">
        {topic.isMarkedForDeletion && (
          <StatusBadge tone="destructive">deleting</StatusBadge>
        )}
        {topic.isCompacted && <StatusBadge tone="warning">compacted</StatusBadge>}
        {topic.isControlTopic && <StatusBadge tone="muted">internal</StatusBadge>}
      </div>

      <Cell label="parts">{topic.partitions}</Cell>
      <Cell
        label="repl"
        tone={topic.replication < 2 ? "warning" : undefined}
      >
        {topic.replication}
      </Cell>
      <Cell label="msgs">{formatNumber(totalMessages)}</Cell>
      {topic.valueType && topic.valueType !== "BYTES" && (
        <Cell label="value" tone="info">
          {topic.valueType}
        </Cell>
      )}
    </li>
  )
}

function Cell({
  label,
  children,
  tone,
}: {
  label: string
  children: React.ReactNode
  tone?: Tone
}) {
  return (
    <div className="flex shrink-0 items-baseline gap-1 tabular-nums">
      <span className={cn("font-mono", tone && TONE_TEXT[tone])}>
        {children}
      </span>
      <span className="text-[9px] uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
    </div>
  )
}
