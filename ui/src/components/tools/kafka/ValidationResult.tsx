import { CircleCheck, CircleX } from "lucide-react"
import { Callout } from "@/components/shared/callout"
import { parseToolResult } from "./parse"
import type { ValidationResultData } from "./types"
import { JsonView } from "../JsonView"

interface Props {
  result: string
}

/**
 * Renders ``validate_connector_configuration`` output - Lenses flattens
 * Connect's PUT-validate response into {class, configuration: [...]} where
 * each entry may carry an ``errors`` array.
 *
 * Important nuance surfaced in the footer: passing validation only means
 * the config is *syntactically* valid against the plugin's ConfigDef. A
 * semantically wrong config (wrong credentials, a topic that doesn't exist)
 * validates clean and still fails at runtime.
 */
export function ValidationResult({ result }: Props) {
  const parsed = parseToolResult<ValidationResultData>(result, ["configuration"])
  if (!parsed.ok || !Array.isArray(parsed.data.configuration)) {
    return <JsonView content={result} />
  }
  const { class: className, configuration } = parsed.data
  const errored = configuration.filter((c) => (c.errors?.length ?? 0) > 0)
  const errorCount = errored.reduce((n, c) => n + (c.errors?.length ?? 0), 0)
  const valid = errorCount === 0

  return (
    <div className="space-y-2">
      <Callout
        variant={valid ? "success" : "destructive"}
        size="sm"
        icon={
          valid ? <CircleCheck className="size-3.5" /> : <CircleX className="size-3.5" />
        }
        title={
          <span className="flex w-full items-center gap-2 normal-case">
            <span>
              {valid
                ? "Configuration valid"
                : `${errorCount} validation error${errorCount === 1 ? "" : "s"}`}
            </span>
            {className && (
              <span
                className="ml-auto truncate font-mono text-[11px] font-normal text-muted-foreground"
                title={className}
              >
                {className.split(".").pop()}
              </span>
            )}
          </span>
        }
      />

      {errored.length > 0 && (
        <div className="divide-y divide-border/60 overflow-hidden rounded-md border border-border/60">
          {errored.map((entry, idx) => (
            <div key={`${entry.name}-${idx}`} className="px-2.5 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs font-semibold">
                  {entry.name}
                </span>
                {entry.value != null && entry.value !== "" && (
                  <span className="truncate font-mono text-xs text-muted-foreground">
                    = {entry.value}
                  </span>
                )}
              </div>
              {entry.errors?.map((err, i) => (
                <p key={i} className="mt-0.5 text-[11px] leading-snug text-destructive">
                  {err}
                </p>
              ))}
            </div>
          ))}
        </div>
      )}

      {valid && (
        <p className="px-1 text-[11px] leading-snug text-muted-foreground italic">
          Valid against the plugin's ConfigDef only - converter/topic format
          mismatches still fail at runtime.
        </p>
      )}
    </div>
  )
}
