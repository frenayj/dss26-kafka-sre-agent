import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { AlertTriangle, Brain, Inbox } from "lucide-react"
import { EmptyState } from "@/components/shared/empty-state"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import type { Row, ToolCall } from "@/lib/types"
import {
  buildEventTree,
  buildParentMap,
  type EventNode,
  type ToolNode,
} from "@/lib/eventTree"
import type { AgentCall } from "@/lib/handoffs"
import { ToolCard } from "./ToolCard"
import { Markdown } from "@/components/tools/Markdown"
import { AgentContextRow, HandoffBlock } from "@/components/handoffs/AgentCallParts"

/** Pixels of slack we allow before considering the user "scrolled up".
 *  Generous threshold lets the user click headers / expand cards
 *  without losing the auto-scroll pin. Forwarded to MessageScroller's
 *  ``scrollEdgeThreshold``. */
const STICKY_THRESHOLD_PX = 120

/** Duration of the post-scroll highlight ring on a focused card. */
const FOCUS_HIGHLIGHT_MS = 1500

/** Bump-counter pattern: clicking the same Timeline row twice should
 *  re-fire the focus action, so we key on both id and bump. */
export interface FocusRequest {
  id: string
  bump: number
}

interface EventStreamProps {
  rows: Row[]
  toolCalls: Map<string, ToolCall>
  autoScroll?: boolean
  /** Latest "scroll to + expand this tool card" request from the Timeline
   *  in the right panel. ``null`` means no active request. */
  focusRequest?: FocusRequest | null
  /** Each sub-agent call's handoff (brief, answer, context), by tool call id. */
  agentCalls?: AgentCall[]
}

/** Sub-agent calls by id, for the containers deep in the tree. */
const AgentCallsContext = createContext<Map<string, AgentCall>>(new Map())

/**
 * Renders the chat feed as a recursive tree that mirrors the call
 * hierarchy: the supervisor's text/reasoning/tool-calls sit at the root;
 * each supervisor → sub-agent call becomes an expandable container whose
 * body holds that sub-agent's own events (text, reasoning, MCP tool
 * calls), recursively.
 *
 * Scrolling is delegated to shadcn's MessageScroller. Auto-follow of the
 * live edge is DISABLED by default (``autoScroll=false``): the feed never
 * slides itself to the bottom, so clicking a tool call in the right-panel
 * Timeline can focus its card without the autoscroll yanking it back down.
 * The user scrolls manually; a jump-to-latest button is still available.
 * Pass ``autoScroll`` to opt back into follow-the-live-edge.
 *
 * Sub-agent containers are open while the underlying tool call is
 * ``pending`` and auto-collapse once it terminates (success / error),
 * unless the user has clicked the header - their click is sticky.
 * MCP tool calls inside a container are always collapsed by default (no
 * auto-expand); the user opens them to drill into the Input / Result / Raw
 * tabs.
 *
 * EventStream owns ALL tool-card open states (containers + leaves) so it
 * can force-open the ancestor chain when the user clicks a row in the
 * right-panel Timeline.
 */
export function EventStream({
  rows,
  toolCalls,
  autoScroll = false,
  focusRequest = null,
  agentCalls,
}: EventStreamProps) {
  const callsById = useMemo(
    () => new Map((agentCalls ?? []).map((c) => [c.id, c])),
    [agentCalls],
  )
  return (
    <MessageScrollerProvider
      autoScroll={autoScroll}
      scrollEdgeThreshold={STICKY_THRESHOLD_PX}
    >
      <AgentCallsContext.Provider value={callsById}>
        <StreamBody rows={rows} toolCalls={toolCalls} focusRequest={focusRequest} />
      </AgentCallsContext.Provider>
    </MessageScrollerProvider>
  )
}

/** Inner body - split out so it renders the scroller viewport, which must
 *  live inside the MessageScrollerProvider. */
function StreamBody({
  rows,
  toolCalls,
  focusRequest = null,
}: Omit<EventStreamProps, "autoScroll" | "agentCalls">) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const tree = useMemo(() => buildEventTree(rows, toolCalls), [rows, toolCalls])
  const parentMap = useMemo(() => buildParentMap(tree), [tree])

  // Per-tool open state. Map key = ToolCall.id. An absent key means
  // "follow the default rule" (sub-agent containers: open while pending;
  // leaves: closed). A present key overrides the default - set by user
  // clicks or by focus requests.
  const [opens, setOpens] = useState<Map<string, boolean>>(new Map())
  const setOpenFor = useCallback((id: string, next: boolean) => {
    setOpens((prev) => {
      const m = new Map(prev)
      m.set(id, next)
      return m
    })
  }, [])
  const getOpen = useCallback(
    (call: ToolCall, isSubAgent: boolean): boolean => {
      const override = opens.get(call.id)
      if (override !== undefined) return override
      return isSubAgent && call.status === "pending"
    },
    [opens],
  )

  // Focus handling. When a Timeline row is clicked, open the focused
  // tool plus every sub-agent ancestor on the way to it (otherwise the
  // child wouldn't be in the DOM to scroll to), then scroll the card
  // into view and flash a highlight ring for confirmation.
  //
  // autoScroll is off, so a plain scrollIntoView sticks - there's no
  // follow-the-live-edge mode to snap us back to the bottom.
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const focusTimerRef = useRef<number | null>(null)
  // Bump of the request we've already scrolled to. parentMap gets a new
  // reference on every stream/replay delta (the tree rebuilds), so without
  // this guard the effect would re-scroll on every delta. parentMap stays in
  // the deps so a request that lands before its target has streamed in
  // retries; once the target is found and scrolled to, its bump is recorded
  // and later runs are no-ops.
  const scrolledBumpRef = useRef<number | null>(null)
  useEffect(() => {
    if (!focusRequest) return
    if (scrolledBumpRef.current === focusRequest.bump) return

    // Walk up the parent chain so the (possibly nested) target is mounted.
    const chain: string[] = [focusRequest.id]
    let cur = parentMap.get(focusRequest.id)
    while (cur) {
      chain.push(cur)
      cur = parentMap.get(cur)
    }
    setOpens((prev) => {
      const m = new Map(prev)
      for (const id of chain) m.set(id, true)
      return m
    })
    setFocusedId(focusRequest.id)
    if (focusTimerRef.current) window.clearTimeout(focusTimerRef.current)
    focusTimerRef.current = window.setTimeout(() => {
      setFocusedId(null)
      focusTimerRef.current = null
    }, FOCUS_HIGHLIGHT_MS)

    // Defer scroll to next frame so React commits the new opens map and any
    // newly-mounted child DOM exists before we query for it.
    const rafId = requestAnimationFrame(() => {
      const el = viewportRef.current?.querySelector(
        `[data-tool-id="${cssEscape(focusRequest.id)}"]`,
      )
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" })
        scrolledBumpRef.current = focusRequest.bump
      }
      // Not in the DOM yet (child still streaming in): leave the bump
      // unrecorded so the next parentMap change retries.
    })
    return () => cancelAnimationFrame(rafId)
  }, [focusRequest, parentMap])

  useEffect(
    () => () => {
      if (focusTimerRef.current) window.clearTimeout(focusTimerRef.current)
    },
    [],
  )

  if (rows.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <EmptyState
          icon={<Inbox />}
          title="Pick an incident, then hit Run."
          description="The agent's investigation streams here in real time."
          className="w-full max-w-sm border-none"
        />
      </div>
    )
  }

  return (
    <MessageScroller className="flex-1">
      <MessageScrollerViewport ref={viewportRef} className="mac-scrollbar">
        <MessageScrollerContent className="gap-3 px-6 py-6">
          {tree.map((node, i) => (
            <MessageScrollerItem
              key={nodeKey(node, i)}
              messageId={nodeKey(node, i)}
            >
              <NodeView
                node={node}
                getOpen={getOpen}
                setOpen={setOpenFor}
                focusedId={focusedId}
              />
            </MessageScrollerItem>
          ))}
        </MessageScrollerContent>
      </MessageScrollerViewport>
      <MessageScrollerButton aria-label="Jump to latest activity" />
    </MessageScroller>
  )
}

interface NodeListProps {
  nodes: EventNode[]
  getOpen: (call: ToolCall, isSubAgent: boolean) => boolean
  setOpen: (id: string, next: boolean) => void
  focusedId: string | null
}

function NodeList({ nodes, getOpen, setOpen, focusedId }: NodeListProps) {
  return (
    <div className="space-y-3">
      {nodes.map((node, i) => (
        <NodeView
          key={nodeKey(node, i)}
          node={node}
          getOpen={getOpen}
          setOpen={setOpen}
          focusedId={focusedId}
        />
      ))}
    </div>
  )
}

function nodeKey(node: EventNode, idx: number): string {
  switch (node.kind) {
    case "tool":
      return `tool:${node.call.id}`
    case "text":
    case "reasoning":
    case "error":
      return `${node.kind}:${node.row.id}`
    default:
      return String(idx)
  }
}

interface NodeViewProps {
  node: EventNode
  getOpen: (call: ToolCall, isSubAgent: boolean) => boolean
  setOpen: (id: string, next: boolean) => void
  focusedId: string | null
}

function NodeView({ node, getOpen, setOpen, focusedId }: NodeViewProps) {
  switch (node.kind) {
    case "text":
      // Stream chunks may be mid-token; react-markdown handles partial
      // markdown gracefully and re-renders as deltas arrive. The measure is
      // capped so prose stays readable when the pane runs wide; tool cards
      // keep the full width.
      return <Markdown content={node.row.content} className="max-w-[72ch]" />
    case "reasoning":
      return (
        <div className="flex gap-2 text-sm text-muted-foreground italic">
          <Brain className="mt-0.5 size-3.5 shrink-0" />
          <Markdown
            content={node.row.content}
            className="text-sm text-muted-foreground italic [&_p]:my-1"
          />
        </div>
      )
    case "tool":
      return (
        <ToolNodeView
          node={node}
          getOpen={getOpen}
          setOpen={setOpen}
          focusedId={focusedId}
        />
      )
    case "error":
      return (
        <div className="flex gap-2 rounded-md border border-destructive/60 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div>
            <div className="font-medium">{node.row.type}</div>
            <div className="text-destructive/90">{node.row.message}</div>
          </div>
        </div>
      )
  }
}

interface ToolNodeViewProps {
  node: ToolNode
  getOpen: (call: ToolCall, isSubAgent: boolean) => boolean
  setOpen: (id: string, next: boolean) => void
  focusedId: string | null
}

function ToolNodeView({ node, getOpen, setOpen, focusedId }: ToolNodeViewProps) {
  const agentCalls = useContext(AgentCallsContext)
  const open = getOpen(node.call, node.isSubAgent)
  const highlight = focusedId === node.call.id

  if (!node.isSubAgent) {
    return (
      <ToolCard
        call={node.call}
        open={open}
        onToggle={() => setOpen(node.call.id, !open)}
        highlight={highlight}
      />
    )
  }

  const isPending = node.call.status === "pending"
  const agentCall = agentCalls.get(node.call.id)
  const returned = node.call.result
  // The answer handed back is the sub-agent's closing text: show it once, in
  // the Returned block, rather than also as the last paragraph of its events.
  const last = node.children[node.children.length - 1]
  const children =
    returned != null && last?.kind === "text" && last.row.content.trim() === returned.trim()
      ? node.children.slice(0, -1)
      : node.children
  return (
    <ToolCard
      call={node.call}
      open={open}
      onToggle={() => setOpen(node.call.id, !open)}
      accentBySubAgent
      highlight={highlight}
    >
      {agentCall && <BriefBlock call={agentCall} />}
      {agentCall && <AgentContextRow call={agentCall} />}
      {children.length === 0 ? (
        returned == null && (
          <div className="text-xs text-muted-foreground italic">
            {isPending ? "Waiting for sub-agent…" : "(no events recorded)"}
          </div>
        )
      ) : (
        <NodeList
          nodes={children}
          getOpen={getOpen}
          setOpen={setOpen}
          focusedId={focusedId}
        />
      )}
      {returned != null && (
        <HandoffBlock
          direction="out"
          label="Returned to supervisor"
          text={returned}
          sender={node.call.name}
        />
      )}
    </ToolCard>
  )
}

/**
 * What the sub-agent was handed. Usually the supervisor's brief verbatim;
 * the reporter's prompt is the supervisor's verdict with the specialists'
 * outputs attached, which only the recorded handoff carries.
 */
function BriefBlock({ call }: { call: AgentCall }) {
  const prompt = call.context?.prompt
  if (prompt != null && prompt.trim() !== call.brief.trim()) {
    const reporter = call.source === "reporter_agent"
    return (
      <HandoffBlock
        direction="in"
        label={reporter ? "Case file from supervisor" : "Prompt received"}
        text={prompt}
        sender="supervisor"
        note={
          reporter
            ? "The supervisor wrote the verdict; the specialists' outputs were attached verbatim."
            : "Built from the supervisor's brief on the way in."
        }
      />
    )
  }
  if (!call.brief && call.status === "pending") return null
  return (
    <HandoffBlock
      direction="in"
      label="Brief from supervisor"
      text={prompt ?? call.brief}
      sender="supervisor"
    />
  )
}

/** CSS.escape() polyfill-equivalent for the limited set of characters
 *  that can appear in our tool-call ids (``${source}:${toolUseId}``).
 *  Quote-escapes the colon and any other selector-special char so the
 *  attribute selector parses correctly. */
function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value)
  }
  return value.replace(/["\\]/g, "\\$&")
}
