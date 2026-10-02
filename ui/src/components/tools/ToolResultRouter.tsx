import { pagerDutyRequest } from "@/lib/pagerduty"
import type { ToolCall } from "@/lib/types"
import { GenericText } from "./GenericText"
import { JsonView } from "./JsonView"
import { SkillActivation } from "./SkillActivation"
import { TriageSummary } from "./TriageSummary"
import { KafkaDiagnosis } from "./KafkaDiagnosis"
import { ForensicsPr } from "./ForensicsPr"
import { ReporterResult } from "./ReporterResult"
import { CreatePageResult } from "./CreatePageResult"
import { KbPageResult, KbSearchResult } from "./KbResults"
import { PostMessageResult } from "./PostMessageResult"
import {
  GitHubCodeSearchResult,
  GitHubCommitResult,
  GitHubCommitsResult,
  GitHubFileResult,
  GitHubPrListResult,
  GitHubPrReadResult,
  GitHubRepoSearchResult,
} from "./GitHubResults"
import { GetIncidentResult } from "./GetIncidentResult"
import { PagerDutyActionResult } from "./PagerDutyActionResult"
import { PagerDutyAlertsResult } from "./PagerDutyAlertsResult"

// Lenses MCP result components
import { EnvironmentHealth } from "./kafka/EnvironmentHealth"
import { EnvironmentList } from "./kafka/EnvironmentList"
import { ConsumerGroups } from "./kafka/ConsumerGroups"
import { ConsumerGroupsByTopic } from "./kafka/ConsumerGroupsByTopic"
import { TopicList } from "./kafka/TopicList"
import { TopicDetail } from "./kafka/TopicDetail"
import { TopicMetadata } from "./kafka/TopicMetadata"
import { TopicPartitions } from "./kafka/TopicPartitions"
import { MessageMetrics } from "./kafka/MessageMetrics"
import { SqlQuery } from "./kafka/SqlQuery"
import { ConnectorList } from "./kafka/ConnectorList"
import { ConnectorDefinition } from "./kafka/ConnectorDefinition"
import { ValidationResult } from "./kafka/ValidationResult"
import { DestructiveAction } from "./kafka/DestructiveAction"

interface ToolResultRouterProps {
  call: ToolCall
}

// All destructive Lenses MCP tools share the same {success, message} result
// shape, so they all route through DestructiveAction.
const DESTRUCTIVE_TOOLS = new Set([
  "update_consumer_group_topic_partition_offset",
  "update_consumer_group_offsets",
  "delete_consumer_group_offsets",
  "delete_consumer_group",
  "delete_consumer_group_topic_partition_offset",
  "add_topic_partitions",
  "restart_kafka_connector_task",
  "set_action_on_kafka_connector",
  "delete_kafka_connector",
  "create_kafka_connector",
  "create_topic",
  "create_topic_with_schema",
  "update_topic_config",
])

/**
 * Switch on tool name and render the matching pretty-printer. Falls back to
 * JsonView for tools whose output is JSON-ish, then GenericText for free
 * text. Adding a new printer means adding a `case` here and creating one
 * component.
 */
export function ToolResultRouter({ call }: ToolResultRouterProps) {
  const content = call.result ?? ""
  if (!content) return null

  switch (call.name) {
    // Sub-agents (supervisor's @tool closures)
    case "triage_agent":
      return <TriageSummary content={content} />
    case "kafka_diagnosis_agent":
      return <KafkaDiagnosis content={content} />
    case "code_forensics_agent":
      return <ForensicsPr content={content} />
    case "reporter_agent":
      return <ReporterResult content={content} />

    // Skills plugin
    case "skills":
      return <SkillActivation input={call.input} content={content} />

    // PagerDuty stub
    case "get_incident":
    case "list_recent_incidents":
      return <GetIncidentResult content={content} />

    // PagerDuty's hosted MCP (live mode) - one read tool and one write tool,
    // each switched by request.action.
    case "browse_incidents":
      switch (pagerDutyRequest(call.input)?.action) {
        case "get":
          return <GetIncidentResult content={content} />
        case "list_alerts":
          return <PagerDutyAlertsResult content={content} />
        default:
          return <JsonView content={content} />
      }
    case "manage_incidents":
      return <PagerDutyActionResult input={call.input} content={content} />

    // GitHub - official github-mcp-server tools (live) and the stub that mirrors them
    case "search_pull_requests":
    case "list_pull_requests":
      return <GitHubPrListResult content={content} />
    case "pull_request_read":
      return <GitHubPrReadResult input={call.input} content={content} />
    case "search_code":
      return <GitHubCodeSearchResult content={content} />
    case "get_file_contents":
      return <GitHubFileResult input={call.input} content={content} />
    case "list_commits":
      return <GitHubCommitsResult content={content} />
    case "get_commit":
      return <GitHubCommitResult content={content} />
    case "search_repositories":
      return <GitHubRepoSearchResult content={content} />

    // Confluence stub
    case "create_page":
      return <CreatePageResult input={call.input} content={content} />
    case "search_pages":
      return <KbSearchResult content={content} />
    case "get_page":
      return <KbPageResult content={content} />

    // Slack stub
    case "post_message":
      return <PostMessageResult input={call.input} content={content} />

    // Lenses MCP - read tools
    case "check_environment_health":
      return <EnvironmentHealth result={content} />
    case "list_environments":
      return <EnvironmentList result={content} />
    case "list_consumer_groups":
      return <ConsumerGroups result={content} />
    case "list_consumer_groups_by_topic":
      return <ConsumerGroupsByTopic result={content} />
    case "list_topics":
    case "list_topic_metadata":
      return <TopicList result={content} />
    case "get_topic":
      return <TopicDetail result={content} />
    case "get_topic_metadata":
      return <TopicMetadata result={content} />
    case "get_topic_partitions":
      return <TopicPartitions result={content} />
    case "get_dataset_message_metrics":
      return <MessageMetrics result={content} />
    case "execute_sql":
      return <SqlQuery result={content} />
    case "list_kafka_connectors":
      return <ConnectorList result={content} />
    case "get_kafka_connector_target_definition":
      return <ConnectorDefinition result={content} />
    case "validate_connector_configuration":
      return <ValidationResult result={content} />

    default:
      if (DESTRUCTIVE_TOOLS.has(call.name)) {
        return <DestructiveAction result={content} />
      }
      return looksLikeJson(content) ? (
        <JsonView content={content} />
      ) : (
        <GenericText content={content} />
      )
  }
}

function looksLikeJson(s: string): boolean {
  const t = s.trimStart()
  return t.startsWith("{") || t.startsWith("[")
}
