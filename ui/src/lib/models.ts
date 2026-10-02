import type { AgentMetrics } from "@/lib/types"
import type { ModelAlias } from "@/lib/api"

/** USD per million tokens. */
interface Rates {
  input: number
  output: number
  /** Cached prompt tokens; uncached input price when the provider has none. */
  cacheRead?: number
  /** Prompt tokens written to the cache; uncached input price when absent. */
  cacheWrite?: number
}

interface Price extends Rates {
  /** Higher rates for a call whose prompt (cached tokens included) passes
   *  ``over`` tokens. */
  long?: Rates & { over: number }
}

/** Tokens, of one call or summed over an agent's calls. */
interface Usage {
  inputTokens: number
  outputTokens: number
  cacheReadTokens?: number
  cacheWriteTokens?: number
}

interface ModelInfo {
  label: string
  price: Price
}

/**
 * The gateway aliases (agent/gateway/litellm.yaml) and what they cost.
 *
 * The prices mirror harness/seed/seed_phoenix_costs.py, which registers the
 * same models in Phoenix: change both together. Check the providers'
 * pricing pages before quoting a cost; a stale entry produces confidently
 * wrong numbers.
 */
export const MODELS: Record<ModelAlias, ModelInfo> = {
  claude: {
    label: "Claude Sonnet 5.5",
    price: { input: 2, cacheRead: 0.1, cacheWrite: 2.5, output: 10 },
  },
  "claude-haiku-5-5": {
    label: "Claude Haiku 5.5",
    price: {
      input: 0.1,
      cacheRead: 0.01,
      cacheWrite: 0.125,
      output: 0.5,
      long: { over: 100_000, input: 0.5, cacheRead: 0.05, cacheWrite: 0.625, output: 2.5 },
    },
  },
  "claude-haiku": {
    label: "Claude Haiku 4.5",
    price: { input: 1, cacheRead: 0.1, cacheWrite: 1.25, output: 5 },
  },
  "mistral-medium": {
    label: "Mistral Medium 3.5",
    price: { input: 1.5, output: 7.5 },
  },
  "mistral-large": {
    label: "Mistral Large",
    price: { input: 2, output: 6 },
  },
  gpt: {
    label: "GPT-4o",
    price: { input: 2.5, cacheRead: 1.25, output: 10 },
  },
}

export function modelInfo(alias: string | undefined): ModelInfo | undefined {
  return alias ? MODELS[alias as ModelAlias] : undefined
}

/** ``inputTokens`` counts every prompt token, cached ones included, so the
 *  cached share is priced separately and taken out. */
function usd(u: Usage, rates: Rates): number {
  const cacheRead = u.cacheReadTokens ?? 0
  const cacheWrite = u.cacheWriteTokens ?? 0
  const uncached = Math.max(0, u.inputTokens - cacheRead - cacheWrite)
  return (
    (uncached * rates.input +
      cacheRead * (rates.cacheRead ?? rates.input) +
      cacheWrite * (rates.cacheWrite ?? rates.input) +
      u.outputTokens * rates.output) /
    1_000_000
  )
}

/**
 * What one agent's tokens cost on ``alias``, in USD, or null for an alias
 * with no price. A model priced by prompt length is priced call by call
 * (at its lower rates if the run has no per-call figures).
 */
export function tokenCostUsd(m: AgentMetrics, alias: string | undefined): number | null {
  const price = modelInfo(alias)?.price
  if (!price) return null
  const { long } = price
  if (!long || !m.calls?.length) return usd(m, price)
  return m.calls.reduce((sum, call) => sum + usd(call, call.inputTokens > long.over ? long : price), 0)
}
