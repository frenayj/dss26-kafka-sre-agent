/**
 * Lenses MCP tool response types.
 *
 * Each interface mirrors a Lenses MCP server JSON payload. Components in
 * this folder run `parseToolResult<T>(result, requiredKeys)` to validate
 * the shape before rendering, so an MCP version skew falls back to the
 * generic JSON view instead of crashing.
 */

import type { TopicTag } from "./parse"

// ---- check_environment_health -----------------------------------------

export interface EnvironmentHealthData {
  environment: string
  healthy: boolean
  agent_connected: boolean
  issues: string[]
  summary?: {
    kafka_brokers: number
    topics: number
    consumers: number
    connectors: number
  }
}

// ---- list_consumer_groups / list_consumer_groups_by_topic -------------

export interface ConsumerGroupItem {
  id: string
  lrn?: string
  state: string
  active?: boolean
  consumers?: unknown[]
  consumersCount?: number
  topicPartitionsCount?: number
  minLag?: number
  maxLag?: number
  coordinator?: { id: number; host: string; port: number; rack?: string }
  application?: string | null
  coverage?: string
  topicPartitions?: TopicPartitionOffset[]
}

export interface TopicPartitionOffset {
  topic: string
  partition: number
  offset: number
  lag: number
}

// ---- get_topic --------------------------------------------------------

export interface TopicDetailData {
  topicName: string
  lrn?: string
  partitions: number
  replication: number
  isControlTopic?: boolean
  isCompacted?: boolean
  keyType?: string
  valueType?: string
  totalMessages?: number
  config?: TopicConfigEntry[]
  consumers?: TopicConsumer[]
  messagesPerPartition?: PartitionMessages[]
  messagesPerSecond?: number
  isMarkedForDeletion?: boolean
  timestamp?: number
  keySchema?: string | null
  keySchemaVersion?: number | null
  valueSchema?: string | null
  valueSchemaVersion?: number | null
  description?: string | null
  tags?: TopicTag[]
  coverage?: string
}

export interface TopicConsumer {
  id: string
  state?: string
  consumersCount?: number
  maxLag?: number
  [key: string]: unknown
}

export interface TopicConfigEntry {
  name: string
  value: string
  isDefault: boolean
  defaultValue?: string | null
  documentation?: string | null
  originalValue?: string
}

export interface PartitionMessages {
  partition: number
  messages: number
  begin: number
  end: number
}

// ---- get_topic_partitions ---------------------------------------------

export interface TopicPartitionsData {
  partitions: PartitionDetail[]
  jmxTimestamp?: number
  jmxLastRetrievedAt?: string
}

export interface PartitionDetail {
  partition: number
  messages: number
  begin: number
  end: number
  leader: number
  preferredLeader?: number
  bytes?: number
  replicas?: ReplicaInfo[] | number[]
  isr?: number[]
}

export interface ReplicaInfo {
  broker: number
  leader: boolean
  inSync: boolean
}

// ---- get_dataset_message_metrics --------------------------------------

export interface MessageMetricPoint {
  date: string
  messages?: number
  messagesCount?: number
}

// ---- execute_sql ------------------------------------------------------

/** MCP shape: each item is {value, metadata, rownum}. SqlQuery also renders
 *  plain column objects. */
export interface SqlResultRow {
  value: Record<string, unknown>
  metadata?: {
    offset?: number
    partition?: number
    timestamp?: number
    topic?: string
    key?: string | null
    headers?: Record<string, string>
    [key: string]: unknown
  }
  rownum?: number
}

// ---- list_kafka_connectors ---------------------------------------------
// Shape captured from Lenses 6.2.2: the HQ proxy returns {"data": [...]}.
// ``trace`` only appears on failed tasks (and not on every Lenses build) -
// the renderer must treat it as a bonus, not a requirement.

export interface ConnectorListData {
  data: ConnectorListItem[]
}

export interface ConnectorListItem {
  name: string
  lrn?: string
  cluster?: string
  state: string
  tasks?: ConnectorTask[]
  className?: string
  type?: string
  author?: string
  icon?: string
}

export interface ConnectorTask {
  id: number
  state: string
  worker_id?: string
  trace?: string
}

// ---- validate_connector_configuration -----------------------------------
// Lenses flattens Connect's PUT-validate response into
// {class, configuration: [{name, required, errors, value, ...}]}.

export interface ValidationResultData {
  class: string
  configuration: ValidationConfigEntry[]
}

export interface ValidationConfigEntry {
  name: string
  required?: boolean
  order?: number
  documentation?: string
  errors?: string[]
  visible?: boolean
  value?: string | null
  defaultValue?: string | null
}

// ---- Destructive tools (shared shape) ---------------------------------

export interface DestructiveActionData {
  success: boolean
  message: string
}

// ---- list_environments ------------------------------------------------

export interface EnvironmentItem {
  name: string
  display_name?: string
  id?: string
  lrn?: string
  tier?: string
  created_at?: string
  status?: {
    agent_connected?: boolean
    agent?: {
      updated_at?: string
      connected_at?: string
      roundtrip_duration?: number
      agent?: {
        hostname?: string
        version?: string
        protocol_version?: string
      }
      metrics?: {
        kafka?: { num_brokers?: number; version?: string }
        data?: {
          num_topics?: number
          num_partitions?: number
          num_schemas?: number
          data_in_bytes_per_sec?: number
          data_out_bytes_per_sec?: number
          data_in_messages_per_sec?: number
          topic_data_total_bytes?: number
        }
        apps?: { num_consumers?: number; num_other_apps?: number }
        connect?: { num_clusters?: number; num_connectors?: number }
        other?: { num_issues?: number }
      }
    }
  }
}

// ---- list_topics ------------------------------------------------------
// Same item shape as TopicDetailData (each topic carries full config), so
// TopicList reuses TopicDetailData for the array element type.
