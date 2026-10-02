import {
  BookOpenText,
  Cpu,
  FileText,
  GitBranch,
  MessageSquare,
  UserRound,
} from "lucide-react"
import {
  ConfluenceLogo,
  GitHubLogo,
  PagerDutyLogo,
  SlackLogo,
} from "@/components/icons/brands"
import { KafkaLogo } from "@/components/icons/kafka"
import { LensesLogo } from "@/components/icons/lenses"
import { LiteLLMLogo } from "@/components/icons/litellm"
import { McpLogo } from "@/components/icons/mcp"
import { StrandsLogo } from "@/components/icons/strands"
import { AnthropicLogo, MistralLogo, OpenAILogo } from "@/components/icons/llm"
import type { ArchFlowEdge, ArchFlowNode } from "./types"

/**
 * The static system graph, laid out as the incident story reads:
 * the P1 page (top-left) pages the human AND triggers the agent; the agent
 * runtime delegates through the MCP layer into the Kafka estate and the
 * GitHub repos; the write-ups loop back to the on-call engineer (bottom-left).
 * The LLM gateway sits above the runtime - every agent's model calls route
 * through it. Scenario mode never moves nodes - it only dims / lights them.
 *
 * Sources: docs/architecture.md, agent/sub_agents/*.
 */

export const ARCH_NODES: ArchFlowNode[] = [
  // ── Groups (must precede their children) ─────────────────────────────
  {
    id: "grp-agent",
    type: "archGroup",
    position: { x: 340, y: 40 },
    selectable: false,
    data: {
      width: 600,
      height: 620,
      label: "SRE agent",
      sublabel: "Strands Agents · supervisor + four specialists",
      icon: StrandsLogo,
    },
  },
  {
    id: "grp-mcp",
    type: "archGroup",
    position: { x: 1030, y: 40 },
    selectable: false,
    data: {
      width: 270,
      height: 670,
      label: "MCP layer",
      sublabel: "5 servers",
      icon: McpLogo,
    },
  },
  {
    id: "grp-kafka",
    type: "archGroup",
    position: { x: 1420, y: 40 },
    selectable: false,
    data: {
      width: 360,
      height: 500,
      label: "Kafka estate",
      sublabel: "Lenses HQ · cards-prod-euw1",
      icon: KafkaLogo,
    },
  },

  // ── The human and the artifacts around them ──────────────────────────
  {
    id: "pd-alert",
    type: "arch",
    position: { x: 0, y: 40 },
    data: {
      label: "PagerDuty P1 page",
      sublabel: "the incident alert",
      icon: PagerDutyLogo,
      kind: "artifact",
      accent: "var(--destructive)",
      alert: true,
      iconMotion: "ring",
      detail:
        "The P1 that starts everything: kafka_consumer_lag CRITICAL on the fraud engine. It pages the on-call engineer and triggers the SRE agent at the same moment.",
    },
  },
  {
    id: "oncall",
    type: "arch",
    position: { x: 0, y: 220 },
    data: {
      label: "On-call engineer",
      sublabel: "gets paged at 2am",
      icon: UserRound,
      kind: "actor",
      detail:
        "Gets paged - and that's the last thing the incident needs from them. Instead of opening runbooks, they watch the agent's investigation stream live; by the time they're at a keyboard, the RCA and the Slack summary are already waiting.",
    },
  },
  {
    id: "rca-page",
    type: "arch",
    position: { x: 360, y: 740 },
    data: {
      label: "Confluence RCA",
      sublabel: "the blameless post-mortem",
      icon: FileText,
      kind: "artifact",
      accent: "var(--agent-reporter)",
      detail:
        "The write-up the reporter publishes: impact, timeline, root cause, and the recommended fix - ready before the on-call engineer has finished logging in.",
    },
  },
  {
    id: "slack-msg",
    type: "arch",
    position: { x: 360, y: 850 },
    data: {
      label: "Slack summary",
      sublabel: "#sre-oncall",
      icon: MessageSquare,
      kind: "artifact",
      accent: "var(--agent-reporter)",
      detail:
        "The short message posted to #sre-oncall: what broke, the root-cause PR, and the next step - the first thing the on-call engineer actually reads.",
    },
  },

  // ── Agent runtime ────────────────────────────────────────────────────
  {
    id: "supervisor",
    type: "arch",
    position: { x: 30, y: 250 },
    parentId: "grp-agent",
    extent: "parent",
    data: {
      label: "Supervisor",
      sublabel: "Strands · incident commander",
      icon: StrandsLogo,
      kind: "agent",
      accent: "var(--agent-supervisor)",
      detail:
        "The incident commander. Owns no MCP server - its only tools are the four specialists, wrapped as sub-agents-as-tools. It sequences the investigation and streams every event, its own and the sub-agents', to the live dashboard.",
      facts: [
        ["Pattern", "sub-agents as tools"],
        ["Source", "agent/sub_agents/supervisor.py"],
        ["Prompt", "agent/prompts/supervisor.md"],
      ],
    },
  },
  {
    id: "triage",
    type: "arch",
    position: { x: 350, y: 70 },
    parentId: "grp-agent",
    extent: "parent",
    data: {
      label: "Triage",
      sublabel: "alert → hard facts",
      icon: StrandsLogo,
      kind: "agent",
      accent: "var(--agent-triage)",
      detail:
        "Reads the PagerDuty incident payload and reduces it to facts the rest of the run builds on: cluster, consumer group / connector, service, severity. Always the first delegation.",
      facts: [
        ["Tool name", "triage_agent"],
        ["MCP", "PagerDuty"],
      ],
    },
  },
  {
    id: "diagnosis",
    type: "arch",
    position: { x: 350, y: 190 },
    parentId: "grp-agent",
    extent: "parent",
    data: {
      label: "Kafka diagnosis",
      sublabel: "live cluster investigation",
      icon: StrandsLogo,
      kind: "agent",
      accent: "var(--agent-diagnosis)",
      detail:
        "The interesting one: talks to Lenses MCP and queries the Kafka cluster live - consumer groups, topics, schemas, connectors, SQL. Loads Lenses Kafka Skills on demand to structure each investigation.",
      facts: [
        ["Tool name", "kafka_diagnosis_agent"],
        ["MCP", "Lenses"],
      ],
    },
  },
  {
    id: "skills",
    type: "arch",
    position: { x: 380, y: 300 },
    parentId: "grp-agent",
    extent: "parent",
    data: {
      label: "Lenses Kafka Skills",
      sublabel: "9 skills · loaded on demand",
      icon: BookOpenText,
      kind: "skills",
      accent: "var(--agent-skills)",
      detail:
        "Markdown runbooks under agent/skills/, activated only when relevant: consumer-lag, schema-review, incident-rca, perf-review, dlq-review, security-audit, topic-audit, connector-review, incident-report. Wired into the two sub-agents that use them: diagnosis (the investigation skills) and reporter (kafka-incident-report).",
      facts: [
        ["Source", "agent/skills/*/SKILL.md"],
        ["Used by", "diagnosis + reporter"],
      ],
    },
  },
  {
    id: "forensics",
    type: "arch",
    position: { x: 350, y: 410 },
    parentId: "grp-agent",
    extent: "parent",
    data: {
      label: "Code forensics",
      sublabel: "PR hunt",
      icon: StrandsLogo,
      kind: "agent",
      accent: "var(--agent-forensics)",
      detail:
        "Hunts the culprit change: lists recent PRs for the implicated service, reads the diffs, and names the PR - even when the title is misleading. Confirms with the exact changed lines.",
      facts: [
        ["Tool name", "code_forensics_agent"],
        ["MCP", "GitHub"],
      ],
    },
  },
  {
    id: "reporter",
    type: "arch",
    position: { x: 350, y: 520 },
    parentId: "grp-agent",
    extent: "parent",
    data: {
      label: "Reporter",
      sublabel: "RCA + on-call summary",
      icon: StrandsLogo,
      kind: "agent",
      accent: "var(--agent-reporter)",
      detail:
        "Writes the blameless RCA to Confluence and posts the short summary to #sre-oncall in Slack, including the recommended next step (e.g. \"revert the culprit PR\").",
      facts: [
        ["Tool name", "reporter_agent"],
        ["MCP", "Confluence + Slack"],
      ],
    },
  },

  // ── MCP layer ────────────────────────────────────────────────────────
  {
    id: "mcp-pagerduty",
    type: "arch",
    position: { x: 25, y: 70 },
    parentId: "grp-mcp",
    extent: "parent",
    data: {
      label: "PagerDuty MCP",
      sublabel: "incident source",
      icon: PagerDutyLogo,
      kind: "mcp",
      accent: "var(--brand-pagerduty)",
      detail:
        "Serves the demo incident - PI7K3FQ, the schema break - to the triage sub-agent.",
    },
  },
  {
    id: "mcp-lenses",
    type: "arch",
    position: { x: 25, y: 190 },
    parentId: "grp-mcp",
    extent: "parent",
    data: {
      label: "Lenses MCP",
      sublabel: "live Kafka tools",
      icon: LensesLogo,
      kind: "mcp",
      accent: "var(--lenses-brand)",
      detail:
        "Calls Lenses HQ with a provisioned service account (OAuth is the fallback for a human-driven run); exposes live tools for topics, consumer groups, schemas, connectors and SQL on cards-prod-euw1.",
      facts: [["Auth", "Service-account key, or OAuth"]],
    },
  },
  {
    id: "mcp-github",
    type: "arch",
    position: { x: 25, y: 410 },
    parentId: "grp-mcp",
    extent: "parent",
    data: {
      label: "GitHub MCP",
      sublabel: "PR history + diffs",
      icon: GitHubLogo,
      kind: "mcp",
      accent: "var(--brand-github)",
      detail:
        "Live: GitHub's official MCP server (read-only) on the private dss26-org org - ~20 repos with real history; the culprit PR is merged by the induce script. Stub: a snapshot of the same org behind the same tool names.",
    },
  },
  {
    id: "mcp-confluence",
    type: "arch",
    position: { x: 25, y: 500 },
    parentId: "grp-mcp",
    extent: "parent",
    data: {
      label: "Confluence MCP",
      sublabel: "RCA pages",
      icon: ConfluenceLogo,
      kind: "mcp",
      accent: "var(--brand-confluence)",
      detail: "Accepts create_page and returns the page the reporter cites in its summary.",
    },
  },
  {
    id: "mcp-slack",
    type: "arch",
    position: { x: 25, y: 580 },
    parentId: "grp-mcp",
    extent: "parent",
    data: {
      label: "Slack MCP",
      sublabel: "#sre-oncall",
      icon: SlackLogo,
      kind: "mcp",
      detail: "Accepts post_message to #sre-oncall - the on-call summary with the next step.",
    },
  },

  // ── Kafka estate ─────────────────────────────────────────────────────
  {
    id: "lenses-hq",
    type: "arch",
    position: { x: 64, y: 60 },
    parentId: "grp-kafka",
    extent: "parent",
    data: {
      label: "Lenses HQ",
      sublabel: "control plane",
      icon: LensesLogo,
      kind: "system",
      accent: "var(--lenses-brand)",
      detail:
        "The Lenses control plane. The cluster's Lenses agent connects here, and the MCP server calls its API with the agent's service account. Applies that identity's role to every request - which environments it can see, and what it can do there. Holds the 32-topic catalogue metadata.",
    },
  },
  {
    id: "agent-prod",
    type: "arch",
    position: { x: 64, y: 170 },
    parentId: "grp-kafka",
    extent: "parent",
    data: {
      label: "Lenses agent",
      sublabel: "cluster link",
      icon: LensesLogo,
      kind: "system",
      accent: "var(--lenses-brand)",
      detail:
        "The Lenses agent that plugs cards-prod-euw1 into HQ - it's what lets Lenses (and therefore the MCP tools) see this cluster's topics, consumer groups, schemas and connectors.",
    },
  },
  {
    id: "kafka-prod",
    type: "arch",
    position: { x: 64, y: 280 },
    parentId: "grp-kafka",
    extent: "parent",
    data: {
      label: "cards-prod-euw1",
      sublabel: "broker · SR · Connect",
      icon: KafkaLogo,
      kind: "system",
      alert: true,
      detail:
        "Kafka + Schema Registry + Kafka Connect. Carries the live cards.authorisation.requested.v1 stream plus the 30-topic cards-platform catalogue, with traffic generated by kafka-connect-datagen. The demo incident fires here.",
    },
  },
  {
    id: "fraud",
    type: "arch",
    position: { x: 64, y: 410 },
    parentId: "grp-kafka",
    extent: "parent",
    data: {
      label: "fraud-decisioning-engine",
      sublabel: "consumer · pinned v1 reader",
      icon: Cpu,
      kind: "system",
      detail:
        "The lag victim: consumes cards.authorisation.requested.v1 pinned to schema v1 and produces cards.ledger.posted.v1. Wedges on the first incompatible v2 record - lag grows and ledger production stops.",
    },
  },

  // ── GitHub repos (behind the GitHub MCP) ─────────────────────────────
  {
    id: "gh-repo",
    type: "arch",
    position: { x: 1484, y: 620 },
    data: {
      label: "GitHub repos",
      sublabel: "the culprit PR lives here",
      icon: GitBranch,
      kind: "artifact",
      accent: "var(--agent-forensics)",
      detail:
        "Where the incident was born: dss26-org/merchant-gateway (the incompatible v2 schema + compatibility NONE), among decoy merges across the org. The forensics sub-agent finds it by search and proves it from the diff.",
    },
  },

  // ── Model plane ──────────────────────────────────────────────────────
  {
    id: "gateway",
    type: "arch",
    position: { x: 532, y: -160 },
    data: {
      label: "LiteLLM gateway",
      sublabel: "one gateway · any provider",
      icon: LiteLLMLogo,
      kind: "gateway",
      detail:
        "Every model call from every agent - the supervisor and all four sub-agents - goes through this single gateway. The model alias picks the provider, so switching models is a dropdown in the dashboard, never a code change.",
      facts: [["Routing", "agent/gateway/litellm.yaml"]],
    },
  },
  {
    id: "anthropic",
    type: "arch",
    position: { x: 260, y: -320 },
    data: {
      label: "Anthropic",
      sublabel: "Claude models",
      icon: AnthropicLogo,
      kind: "system",
      accent: "#D97757",
      detail:
        "Claude Sonnet 5.5 behind the default claude alias - the supervisor and all four sub-agents run on it out of the box. Claude Haiku 5.5 and Haiku 4.5 sit behind claude-haiku-5-5 and claude-haiku for lighter roles.",
    },
  },
  {
    id: "mistral",
    type: "arch",
    position: { x: 532, y: -320 },
    data: {
      label: "Mistral AI",
      sublabel: "Mistral models",
      icon: MistralLogo,
      kind: "system",
      accent: "#FA520F",
      detail:
        "Mistral Medium 3.5 and Mistral Large behind the mistral-medium and mistral-large aliases. Repoint any role from the dashboard's Models panel and the gateway does the rest.",
    },
  },
  {
    id: "openai",
    type: "arch",
    position: { x: 804, y: -320 },
    data: {
      label: "OpenAI",
      sublabel: "GPT models",
      icon: OpenAILogo,
      kind: "system",
      accent: "var(--foreground)",
      detail:
        "GPT-4o behind the gpt alias - same dropdown, same gateway, zero code changes to switch.",
    },
  },
]

/** All edges default to type "flow"; handle ids: l/t/rt/bt targets, r/b/ls/ts sources. */
export const ARCH_EDGES: ArchFlowEdge[] = [
  // The page fans out: human + agent.
  {
    id: "e-alert-oncall",
    source: "pd-alert",
    target: "oncall",
    sourceHandle: "b",
    targetHandle: "t",
    type: "flow",
    data: { label: "pages", accent: "var(--destructive)" },
  },
  {
    id: "e-alert-agent",
    source: "pd-alert",
    target: "supervisor",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "triggers", accent: "var(--agent-supervisor)" },
  },

  // Supervisor → specialists.
  {
    id: "e-sup-triage",
    source: "supervisor",
    target: "triage",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "triage_agent", accent: "var(--agent-triage)" },
  },
  {
    id: "e-sup-diagnosis",
    source: "supervisor",
    target: "diagnosis",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "kafka_diagnosis_agent", accent: "var(--agent-diagnosis)" },
  },
  {
    id: "e-sup-forensics",
    source: "supervisor",
    target: "forensics",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "code_forensics_agent", accent: "var(--agent-forensics)" },
  },
  {
    id: "e-sup-reporter",
    source: "supervisor",
    target: "reporter",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "reporter_agent", accent: "var(--agent-reporter)" },
  },
  {
    id: "e-diagnosis-skills",
    source: "diagnosis",
    target: "skills",
    sourceHandle: "b",
    targetHandle: "t",
    type: "flow",
    data: { accent: "var(--agent-skills)" },
  },
  {
    id: "e-reporter-skills",
    source: "reporter",
    target: "skills",
    sourceHandle: "r",
    targetHandle: "rt",
    type: "flow",
    data: { accent: "var(--agent-skills)" },
  },

  // Specialists → their MCP servers.
  {
    id: "e-triage-pd",
    source: "triage",
    target: "mcp-pagerduty",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "get_incident", accent: "var(--agent-triage)" },
  },
  {
    id: "e-diagnosis-lenses",
    source: "diagnosis",
    target: "mcp-lenses",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "live cluster tools", accent: "var(--agent-diagnosis)" },
  },
  {
    id: "e-forensics-github",
    source: "forensics",
    target: "mcp-github",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "recent PRs + diffs", accent: "var(--agent-forensics)" },
  },
  {
    id: "e-reporter-confluence",
    source: "reporter",
    target: "mcp-confluence",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "create_page", accent: "var(--agent-reporter)" },
  },
  {
    id: "e-reporter-slack",
    source: "reporter",
    target: "mcp-slack",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "post_message", accent: "var(--agent-reporter)" },
  },

  // Lenses MCP → the estate, via HQ and the cluster's Lenses agent. Edges
  // are drawn caller → callee; for reads the pulse runs back with the data
  // (pulse: "toSource"), so cluster status flows to the MCP server.
  {
    id: "e-lenses-hq",
    source: "mcp-lenses",
    target: "lenses-hq",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: {
      label: "API",
      accent: "var(--agent-diagnosis)",
      turnX: 1360,
      pulse: "toSource",
    },
  },
  {
    id: "e-hq-aprod",
    source: "lenses-hq",
    target: "agent-prod",
    sourceHandle: "b",
    targetHandle: "t",
    type: "flow",
    data: { accent: "var(--agent-diagnosis)", pulse: "toSource" },
  },
  {
    id: "e-aprod-prod",
    source: "agent-prod",
    target: "kafka-prod",
    sourceHandle: "b",
    targetHandle: "t",
    type: "flow",
    data: { accent: "var(--agent-diagnosis)", pulse: "toSource" },
  },
  {
    id: "e-prod-fraud",
    source: "kafka-prod",
    target: "fraud",
    sourceHandle: "b",
    targetHandle: "t",
    type: "flow",
    data: { label: "auth stream → ledger", accent: "var(--destructive)" },
  },

  // GitHub MCP → the repos it mirrors.
  {
    id: "e-github-repo",
    source: "mcp-github",
    target: "gh-repo",
    sourceHandle: "r",
    targetHandle: "l",
    type: "flow",
    data: { label: "search · diff", accent: "var(--agent-forensics)", pulse: "toSource" },
  },

  // The write-ups loop back to the human.
  {
    id: "e-confluence-rca",
    source: "mcp-confluence",
    target: "rca-page",
    sourceHandle: "b",
    targetHandle: "rt",
    type: "flow",
    data: { label: "publishes", accent: "var(--agent-reporter)" },
  },
  {
    id: "e-slack-msg",
    source: "mcp-slack",
    target: "slack-msg",
    sourceHandle: "b",
    targetHandle: "rt",
    type: "flow",
    data: { label: "posts", accent: "var(--agent-reporter)" },
  },
  {
    id: "e-rca-oncall",
    source: "rca-page",
    target: "oncall",
    sourceHandle: "ls",
    targetHandle: "l",
    type: "flow",
    data: { label: "to review", accent: "var(--agent-reporter)" },
  },
  {
    id: "e-slack-oncall",
    source: "slack-msg",
    target: "oncall",
    sourceHandle: "ls",
    targetHandle: "l",
    type: "flow",
    data: { label: "notifies", accent: "var(--agent-reporter)" },
  },

  // Model plane: every agent's calls, via the group; the gateway routes to
  // whichever provider the alias names. The pulse runs back to the agents
  // with the model's response.
  {
    id: "e-agents-gateway",
    source: "grp-agent",
    target: "gateway",
    sourceHandle: "ts",
    targetHandle: "bt",
    type: "flow",
    data: {
      label: "every model call · all agents",
      accent: "var(--warning)",
      dashed: true,
      pulse: "toSource",
    },
  },
  {
    id: "e-gw-anthropic",
    source: "gateway",
    target: "anthropic",
    sourceHandle: "ts",
    targetHandle: "bt",
    type: "flow",
    data: { label: "claude", accent: "#D97757", dashed: true, pulse: "toSource" },
  },
  {
    id: "e-gw-mistral",
    source: "gateway",
    target: "mistral",
    sourceHandle: "ts",
    targetHandle: "bt",
    type: "flow",
    data: { label: "mistral-medium", accent: "#FA520F", dashed: true, pulse: "toSource" },
  },
  {
    id: "e-gw-openai",
    source: "gateway",
    target: "openai",
    sourceHandle: "ts",
    targetHandle: "bt",
    type: "flow",
    data: { label: "gpt", accent: "var(--foreground)", dashed: true, pulse: "toSource" },
  },
]
