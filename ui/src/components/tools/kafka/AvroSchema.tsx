import { CodeBlock } from "@/components/shared/code-block"
import { Expander } from "@/components/shared/expander"
import { KeyValueList } from "@/components/shared/key-value-list"
import type { AvroField } from "./parse"

function renderAvroType(t: unknown): string {
  if (typeof t === "string") return t
  if (Array.isArray(t)) return t.map((x) => renderAvroType(x)).join(" | ")
  if (t && typeof t === "object") {
    const obj = t as { type?: unknown; logicalType?: string; items?: unknown }
    if (obj.logicalType) return `${renderAvroType(obj.type)} (${obj.logicalType})`
    if (obj.type === "array" && obj.items != null)
      return `array<${renderAvroType(obj.items)}>`
    if (obj.type) return renderAvroType(obj.type)
  }
  return String(t)
}

function prettyJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

export function AvroSchemaSection({
  fields,
  raw,
  label = "Value schema",
}: {
  fields: AvroField[]
  raw: string
  label?: string
}) {
  return (
    <div className="space-y-1.5">
      <span className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
        {label} ({fields.length} field{fields.length === 1 ? "" : "s"})
      </span>
      <KeyValueList
        rows={fields.map((f) => ({
          key: (
            <>
              <span className="block truncate font-semibold">{f.name}</span>
              {f.doc && (
                <span
                  className="block truncate font-sans text-[11px] font-normal leading-snug text-muted-foreground"
                  title={f.doc}
                >
                  {f.doc}
                </span>
              )}
            </>
          ),
          value: <span className="text-info">{renderAvroType(f.type)}</span>,
        }))}
      />
      <Expander label="raw">
        <CodeBlock className="text-muted-foreground">{prettyJson(raw)}</CodeBlock>
      </Expander>
    </div>
  )
}
