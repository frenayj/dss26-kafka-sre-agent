import { Hash, Bot, Check } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { safeParseJson } from "@/lib/format"
import { Markdown } from "./Markdown"

interface PostMessageResultProps {
  input: unknown
  content: string
}

function parseInput(input: unknown): { channel: string | null; text: string | null } {
  if (input == null) return { channel: null, text: null }
  const obj =
    typeof input === "string" ? safeParseJson(input) : (input as Record<string, unknown>)
  if (!obj || typeof obj !== "object") return { channel: null, text: null }
  return {
    channel: typeof obj.channel === "string" ? obj.channel : null,
    text: typeof obj.text === "string" ? obj.text : null,
  }
}

function parseAck(content: string): {
  ok: boolean
  channel: string | null
  ts: string | null
} {
  const v = safeParseJson(content)
  if (!v) return { ok: false, channel: null, ts: null }
  return {
    ok: v.ok === true,
    channel: typeof v.channel === "string" ? v.channel : null,
    ts: typeof v.ts === "string" || typeof v.ts === "number" ? String(v.ts) : null,
  }
}

/** Slack ``ts`` is epoch seconds (float). Render as a Slack-style clock. */
function formatSlackTime(ts: string | null): string | null {
  if (!ts) return null
  const secs = Number.parseFloat(ts)
  if (!Number.isFinite(secs)) return null
  const d = new Date(secs * 1000)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
}

/** Strip the leading ``#`` so we can render our own. */
function bareChannel(name: string): string {
  return name.replace(/^#+/, "")
}

export function PostMessageResult({ input, content }: PostMessageResultProps) {
  const { channel: inputChannel, text } = parseInput(input)
  const ack = parseAck(content)
  const channel = inputChannel ?? ack.channel
  const time = formatSlackTime(ack.ts)

  return (
    <div className="rounded-lg border border-border bg-card/40 overflow-hidden">
      {/* Channel header bar */}
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border/60 bg-muted/30">
        <Hash className="size-3.5 text-muted-foreground shrink-0" />
        <span className="text-xs font-semibold truncate">
          {channel ? bareChannel(channel) : "channel"}
        </span>
        {ack.ok && (
          <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-success shrink-0">
            <Check className="size-3" /> sent
          </span>
        )}
      </div>

      {/* Message row: app avatar + sender line + body */}
      <div className="flex gap-2.5 px-3 py-2.5">
        <div className="size-9 shrink-0 rounded-md bg-gradient-to-br from-[#611f69] to-[#ca3a6f] flex items-center justify-center">
          <Bot className="size-5 text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-sm font-bold text-foreground">Kafka SRE Agent</span>
            <Badge
              variant="secondary"
              className="rounded-sm px-1 py-px text-[9px] font-bold uppercase tracking-wide"
            >
              App
            </Badge>
            {time && <span className="text-[11px] text-muted-foreground">{time}</span>}
          </div>
          {text ? (
            <Markdown content={text} className="mt-0.5" />
          ) : (
            <p className="mt-0.5 text-xs italic text-muted-foreground">(no message text)</p>
          )}
        </div>
      </div>
    </div>
  )
}
