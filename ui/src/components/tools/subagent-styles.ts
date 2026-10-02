import type { ComponentType } from "react"
import { Bot } from "lucide-react"
import { KafkaLogo } from "@/components/icons/kafka"
import {
  ConfluenceLogo,
  GitHubLogo,
  PagerDutyLogo,
} from "@/components/icons/brands"

/**
 * Source → display config. `source` is `"supervisor"` for the top-level
 * agent, or a closure name for sub-agents (matches the `source` tag emitted
 * by agent/server.py).
 *
 * Accents are CSS variables defined in src/index.css (`--agent-*`). Keeping
 * them as `var(...)` strings means we can drop them straight into inline
 * styles for the colored rail / dot, and they live in one place.
 *
 * Each specialist wears the mark of the service it owns (PagerDuty, Kafka,
 * GitHub, Confluence). Triage and reporter take that brand's colour;
 * diagnosis takes the Lenses orange (it works Kafka through Lenses MCP) and
 * forensics keeps purple, since GitHub's mark is black.
 */
export interface SourceStyle {
  label: string
  short: string
  icon: ComponentType<{ className?: string }>
  accent: string // CSS variable expression, e.g. "var(--agent-triage)"
}

const SOURCE_STYLES: Record<string, SourceStyle> = {
  supervisor: {
    label: "Supervisor",
    short: "supervisor",
    icon: Bot,
    accent: "var(--agent-supervisor)",
  },
  triage_agent: {
    label: "Triage",
    short: "triage",
    icon: PagerDutyLogo,
    accent: "var(--agent-triage)",
  },
  kafka_diagnosis_agent: {
    label: "Kafka diagnosis",
    short: "diagnosis",
    icon: KafkaLogo,
    accent: "var(--agent-diagnosis)",
  },
  code_forensics_agent: {
    label: "Code forensics",
    short: "forensics",
    icon: GitHubLogo,
    accent: "var(--agent-forensics)",
  },
  reporter_agent: {
    label: "Reporter",
    short: "reporter",
    icon: ConfluenceLogo,
    accent: "var(--agent-reporter)",
  },
}

const FALLBACK: SourceStyle = {
  label: "Agent",
  short: "agent",
  icon: Bot,
  accent: "var(--muted-foreground)",
}

export function sourceStyle(source: string): SourceStyle {
  return SOURCE_STYLES[source] ?? FALLBACK
}
