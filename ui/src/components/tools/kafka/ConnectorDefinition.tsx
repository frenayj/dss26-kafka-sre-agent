import { CodeBlock } from "@/components/shared/code-block"
import { Expander } from "@/components/shared/expander"
import { KeyValueList } from "@/components/shared/key-value-list"
import { StatusBadge } from "@/components/shared/status-badge"
import { cn } from "@/lib/utils"
import { stateToTone } from "./parse"

interface Props {
  result: string
}

/**
 * Renders the YAML ``KafkaConnector`` resource returned by
 * ``get_kafka_connector_target_definition``:
 *
 *   apiVersion: lenses.io/v0beta
 *   kind: KafkaConnector
 *   spec:
 *     state: RUNNING
 *     cluster: fast-data-dev
 *     name: orders-sink
 *     config:
 *       connector.class: ...
 *       value.converter: ...
 *
 * We parse it line-by-line (the shape is flat enough that a YAML library
 * would be overkill) and accent the properties that decide most connector
 * incidents: converters, schema-registry wiring, KCQL, error handling.
 * Anything that doesn't look like this resource falls back to a raw block.
 */

interface ParsedDefinition {
  name?: string
  cluster?: string
  state?: string
  config: Array<{ key: string; value: string }>
}

/** Properties worth the reviewer's eyes first - accented in the list. */
const INTERESTING_KEYS = [
  /^key\.converter$/,
  /^value\.converter$/,
  /converter\..*schema\.registry\.url$/,
  /converter\.schemas\.enable$/,
  /^connect\..*\.kcql$/,
  /^errors\.tolerance$/,
  /^errors\.deadletterqueue\./,
  /^transforms$/,
]

function isInteresting(key: string): boolean {
  return INTERESTING_KEYS.some((re) => re.test(key))
}

function parseDefinition(raw: string): ParsedDefinition | null {
  if (!raw.includes("kind: KafkaConnector")) return null
  const lines = raw.split("\n")
  const out: ParsedDefinition = { config: [] }

  let configIndent: number | null = null
  for (const line of lines) {
    if (!line.trim() || line.trimStart().startsWith("#")) continue
    const indent = line.length - line.trimStart().length
    const trimmed = line.trim()

    if (configIndent !== null) {
      if (indent <= configIndent) {
        configIndent = null // left the config block
      } else {
        const sep = trimmed.indexOf(":")
        if (sep > 0) {
          const key = trimmed.slice(0, sep).trim()
          const value = stripQuotes(trimmed.slice(sep + 1).trim())
          out.config.push({ key, value })
        } else if (out.config.length > 0) {
          // No colon - a wrapped continuation of the previous value (long
          // KCQL statements fold across lines in the YAML the API returns).
          const last = out.config[out.config.length - 1]
          last.value = `${last.value} ${trimmed}`.trim()
        }
        continue
      }
    }

    if (trimmed === "config:") {
      configIndent = indent
      continue
    }
    const sep = trimmed.indexOf(":")
    if (sep > 0) {
      const key = trimmed.slice(0, sep).trim()
      const value = stripQuotes(trimmed.slice(sep + 1).trim())
      if (key === "name" && !out.name) out.name = value
      if (key === "cluster" && !out.cluster) out.cluster = value
      if (key === "state" && !out.state) out.state = value
    }
  }

  return out.config.length > 0 ? out : null
}

function stripQuotes(v: string): string {
  if (v.length >= 2 && ((v.startsWith("'") && v.endsWith("'")) || (v.startsWith('"') && v.endsWith('"')))) {
    return v.slice(1, -1)
  }
  return v
}

export function ConnectorDefinition({ result }: Props) {
  const parsed = parseDefinition(result)
  if (!parsed) {
    // Unexpected shape - still YAML/text, so show it rather than nothing.
    return <CodeBlock className="text-muted-foreground">{result}</CodeBlock>
  }

  // Interesting keys first (in config order), the rest after.
  const interesting = parsed.config.filter((e) => isInteresting(e.key))
  const rest = parsed.config.filter((e) => !isInteresting(e.key))
  const ordered = [...interesting, ...rest]

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-xs font-semibold">Connector config</span>
        {parsed.name && (
          <span className="truncate font-mono text-xs text-muted-foreground">
            {parsed.name}
            {parsed.cluster ? ` @ ${parsed.cluster}` : ""}
          </span>
        )}
        {parsed.state && (
          <StatusBadge tone={stateToTone(parsed.state)} className="shrink-0">
            {parsed.state}
          </StatusBadge>
        )}
      </div>

      <KeyValueList
        rows={ordered.map((entry) => {
          const accent = isInteresting(entry.key)
          return {
            accent,
            key: (
              <span className={cn(accent && "font-semibold text-warning")}>
                {entry.key}
              </span>
            ),
            value: <span title={entry.value}>{entry.value || "-"}</span>,
          }
        })}
      />

      <Expander label="yaml">
        <CodeBlock className="text-muted-foreground">{result}</CodeBlock>
      </Expander>
    </div>
  )
}
