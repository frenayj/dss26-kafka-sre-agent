import type { ComponentType } from "react"
import { safeParseJson } from "@/lib/format"
import { pagerDutyRequest } from "@/lib/pagerduty"
import { BookOpen, Wrench } from "lucide-react"
import { LensesLogo } from "@/components/icons/lenses"
import { KafkaLogo } from "@/components/icons/kafka"
import {
  ConfluenceLogo,
  GitHubLogo,
  PagerDutyLogo,
  SlackLogo,
} from "@/components/icons/brands"

type AnyIcon = ComponentType<{ className?: string }>

/**
 * Per-tool display config. Covers the tools that actually appear in this
 * demo:
 *   - the 4 sub-agent closures (called by the supervisor)
 *   - the `skills` plugin tool (used by the diagnosis sub-agent)
 *   - PagerDuty / GitHub / Confluence / Slack stub MCP tools
 *   - every Lenses MCP tool (the diagnosis sub-agent uses the reads)
 *
 * Destructive Lenses operations are flagged so the card can render them
 * with a red border; nothing in this read-only demo actually triggers them
 * yet, but the styling is here in case the prompt is loosened.
 */
export interface ToolStyle {
  label: string
  icon: AnyIcon
  /** Text-colour class for brand marks; wins over the destructive red.
   *  Leaf icons default to muted. */
  tint?: string
  destructive?: boolean
}

const N: Pick<ToolStyle, never> = {}
const DEST: Pick<ToolStyle, "destructive"> = { destructive: true }
const PD: Pick<ToolStyle, "icon" | "tint"> = { icon: PagerDutyLogo, tint: "text-brand-pagerduty" }
const GH: Pick<ToolStyle, "icon" | "tint"> = { icon: GitHubLogo, tint: "text-brand-github" }
const CF: Pick<ToolStyle, "icon" | "tint"> = { icon: ConfluenceLogo, tint: "text-brand-confluence" }
const LENSES: Pick<ToolStyle, "icon" | "tint"> = { icon: LensesLogo, tint: "text-lenses-brand" }

const TOOL_STYLES: Record<string, ToolStyle> = {
  // Supervisor's sub-agent closures - same marks as subagent-styles.ts.
  triage_agent: { label: "Triage", icon: PagerDutyLogo, ...N },
  kafka_diagnosis_agent: { label: "Kafka diagnosis", icon: KafkaLogo, ...N },
  code_forensics_agent: { label: "Code forensics", icon: GitHubLogo, ...N },
  reporter_agent: { label: "Reporter", icon: ConfluenceLogo, ...N },

  // Lenses Skills plugin - single tool, the skill name is in the input arg
  skills: { label: "Skill activation", icon: BookOpen },

  // PagerDuty stub MCP
  get_incident: { label: "PagerDuty: incident", ...PD },
  list_recent_incidents: { label: "PagerDuty: recent", ...PD },

  // PagerDuty hosted MCP (live mode)
  // Labelled by request.action when the input names one (see toolStyle).
  browse_incidents: { label: "PagerDuty: browse incidents", ...PD },
  manage_incidents: { label: "PagerDuty: manage incidents", ...PD },

  // GitHub - official github-mcp-server tools (live) and the mirroring stub.
  // Named after the tool; pull_request_read after its method (see toolStyle).
  search_pull_requests: { label: "GitHub: search pull requests", ...GH },
  list_pull_requests: { label: "GitHub: list pull requests", ...GH },
  pull_request_read: { label: "GitHub: pull request read", ...GH },
  search_code: { label: "GitHub: search code", ...GH },
  get_file_contents: { label: "GitHub: get file contents", ...GH },
  list_commits: { label: "GitHub: list commits", ...GH },
  get_commit: { label: "GitHub: get commit", ...GH },
  search_repositories: { label: "GitHub: search repositories", ...GH },

  // Confluence MCP - knowledge-base reads (triage) and the RCA write (reporter)
  search_pages: { label: "Confluence: search", ...CF },
  get_page: { label: "Confluence: page", ...CF },
  create_page: { label: "Confluence: RCA page", ...CF },

  // Slack stub MCP - the mark carries its own four colours, no tint.
  post_message: { label: "Slack: post", icon: SlackLogo },

  // Lenses MCP - every tool wears the Lenses mark (the favicon) in the
  // Lenses orange. Covers the server's full tool set (45 tools).
  check_environment_health: { label: "Lenses: health", ...LENSES },
  list_environments: { label: "Lenses: environments", ...LENSES },
  get_environment: { label: "Lenses: environment", ...LENSES },
  get_deployment_targets: { label: "Lenses: deployment targets", ...LENSES },
  list_topics: { label: "Lenses: topics", ...LENSES },
  get_topic: { label: "Lenses: topic", ...LENSES },
  get_topic_partitions: { label: "Lenses: partitions", ...LENSES },
  get_topic_broker_configs: { label: "Lenses: broker configs", ...LENSES },
  list_topic_metadata: { label: "Lenses: topic metadata", ...LENSES },
  get_topic_metadata: { label: "Lenses: topic metadata", ...LENSES },
  list_consumer_groups: { label: "Lenses: consumer groups", ...LENSES },
  list_consumer_groups_by_topic: { label: "Lenses: lag by topic", ...LENSES },
  get_dataset: { label: "Lenses: dataset", ...LENSES },
  list_datasets: { label: "Lenses: datasets", ...LENSES },
  get_dataset_message_metrics: { label: "Lenses: metrics", ...LENSES },
  execute_sql: { label: "Lenses: SQL", ...LENSES },
  list_kafka_connectors: { label: "Lenses: connectors", ...LENSES },
  get_kafka_connector_target_definition: { label: "Lenses: connector config", ...LENSES },
  validate_connector_configuration: { label: "Lenses: validate connector", ...LENSES },
  list_sql_processors: { label: "Lenses: SQL processors", ...LENSES },
  get_sql_processor: { label: "Lenses: SQL processor", ...LENSES },
  get_pod_logs: { label: "Lenses: pod logs", ...LENSES },
  list_approval_requests: { label: "Lenses: approval requests", ...LENSES },
  get_approval_request: { label: "Lenses: approval request", ...LENSES },

  // Lenses MCP - writes (none used in this demo; here for completeness).
  // The icon stays Lenses orange; the card's red border flags the write.
  update_consumer_partition_offset: { label: "Lenses: set offset", ...LENSES, ...DEST },
  update_consumer_group_offsets: { label: "Lenses: reset offsets", ...LENSES, ...DEST },
  delete_consumer_group_offsets: { label: "Lenses: delete offsets", ...LENSES, ...DEST },
  delete_consumer_partition_offset: { label: "Lenses: delete offset", ...LENSES, ...DEST },
  delete_consumer_group: { label: "Lenses: delete group", ...LENSES, ...DEST },
  add_topic_partitions: { label: "Lenses: add partitions", ...LENSES, ...DEST },
  create_topic: { label: "Lenses: create topic", ...LENSES, ...DEST },
  create_topic_with_schema: { label: "Lenses: create topic+schema", ...LENSES, ...DEST },
  request_topic_creation: { label: "Lenses: request topic", ...LENSES, ...DEST },
  update_topic_config: { label: "Lenses: update topic", ...LENSES, ...DEST },
  update_topic_metadata: { label: "Lenses: update topic metadata", ...LENSES, ...DEST },
  update_dataset_topic_description: { label: "Lenses: set description", ...LENSES, ...DEST },
  update_dataset_topic_tags: { label: "Lenses: set tags", ...LENSES, ...DEST },
  resend_message: { label: "Lenses: resend message", ...LENSES, ...DEST },
  create_kafka_connector: { label: "Lenses: create connector", ...LENSES, ...DEST },
  delete_kafka_connector: { label: "Lenses: delete connector", ...LENSES, ...DEST },
  restart_kafka_connector_task: { label: "Lenses: restart task", ...LENSES, ...DEST },
  set_action_on_kafka_connector: { label: "Lenses: connector action", ...LENSES, ...DEST },
  create_sql_processor: { label: "Lenses: create SQL processor", ...LENSES, ...DEST },
  delete_sql_processor: { label: "Lenses: delete SQL processor", ...LENSES, ...DEST },
  create_environment: { label: "Lenses: create environment", ...LENSES, ...DEST },
}

const FALLBACK: ToolStyle = { label: "Tool", icon: Wrench }

/** The ``request.action`` of a PagerDuty MCP call. Reads a partial input
 *  string too, so the label is right while the call is still streaming. */
export function pagerDutyAction(input: unknown): string | null {
  const action = pagerDutyRequest(input)?.action
  if (typeof action === "string") return action
  const match = typeof input === "string" ? input.match(/"action"\s*:\s*"([^"]+)"/) : null
  return match ? match[1] : null
}

/** The ``method`` of a ``pull_request_read`` call, from a partial input too. */
export function pullRequestMethod(input: unknown): string | null {
  const obj = typeof input === "string" ? safeParseJson(input) : input
  const method = obj && typeof obj === "object" ? (obj as Record<string, unknown>).method : null
  if (typeof method === "string") return method
  const match = typeof input === "string" ? input.match(/"method"\s*:\s*"([^"]+)"/) : null
  return match ? match[1] : null
}

/** The action a call asked for, for the tools that switch on an input field:
 *  PagerDuty's two tools on ``request.action``, ``pull_request_read`` on
 *  ``method``. Null for every other tool, or before the field has streamed. */
function actionLabel(name: string, input: unknown): string | null {
  const words = (s: string) => s.replace(/_/g, " ")
  if (name === "browse_incidents" || name === "manage_incidents") {
    const action = pagerDutyAction(input)
    return action ? `PagerDuty: ${words(action)}` : null
  }
  if (name === "pull_request_read") {
    const method = pullRequestMethod(input)
    if (!method) return null
    return `GitHub: ${method === "get" ? "get pull request" : words(method)}`
  }
  return null
}

/** A tool's display config. ``input`` lets the label name the action a call
 *  asked for, where one tool covers several (see actionLabel). */
export function toolStyle(name: string | undefined | null, input?: unknown): ToolStyle {
  if (!name) return FALLBACK
  const style = TOOL_STYLES[name] ?? { ...FALLBACK, label: name }
  const label = actionLabel(name, input)
  return label ? { ...style, label } : style
}

/** Best-effort skill-name extraction for the `skills` tool's input arg. */
export function extractSkillName(input: unknown): string | null {
  if (input == null) return null
  const obj =
    typeof input === "string"
      ? safeParseJson(input)
      : (input as Record<string, unknown>)
  if (obj && typeof obj === "object" && typeof (obj as Record<string, unknown>).skill_name === "string") {
    return (obj as Record<string, string>).skill_name
  }
  if (typeof input === "string") {
    const match = input.match(/"skill_name"\s*:\s*"([^"]*)/)
    if (match) return match[1]
  }
  return null
}

