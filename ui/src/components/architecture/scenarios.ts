import type { Scenario } from "./types"

/**
 * Each demo incident as a step-by-step walkthrough, keyed by scenario id - a
 * new scenario is one more entry. Node / edge ids refer to graph.ts; each step
 * lights its subset and dims the rest. Content follows docs/scenarios.md and
 * the induce/reset scripts in harness/scenarios/.
 */

/** The same beat in every scenario: the page, not a human, starts the agent. */
const TRIGGER_STEP = {
  id: "trigger",
  title: "The page triggers the agent",
  narration:
    "No human presses anything: the P1 kicks off the supervisor directly. It picks up the incident and starts delegating while the on-call engineer is still reaching for their laptop.",
  nodes: ["pd-alert", "supervisor"],
  edges: ["e-alert-agent"],
}

export const SCENARIOS: Record<string, Scenario> = {
  "consumer-lag": {
    id: "consumer-lag",
    incidentId: "PI7K3FQ",
    title: "Schema break",
    alert: "kafka_consumer_lag CRITICAL · fraud-decisioning-engine",
    steps: [
      {
        id: "ship",
        title: "Afternoon - the producer change merges",
        narration:
          "ravi.iyer merges “publish amount as a decimal string, drop country” in dss26-org/merchant-gateway - the producer, not the paged service. The registry refused the new schema as incompatible, so the PR also sets the subject's compatibility to NONE; the release pipeline registers v2 on prod. The consumer-side change it depended on is still an open PR.",
        nodes: ["gh-repo", "kafka-prod"],
        edges: [],
      },
      {
        id: "wedge",
        title: "The consumer wedges",
        narration:
          "fraud-decisioning-engine is pinned to schema v1. The first v2 record fails deserialization; the group stops committing, lag climbs, and ledger production halts - while healthy traffic keeps flowing into the topic.",
        nodes: ["kafka-prod", "fraud"],
        edges: ["e-prod-fraud"],
      },
      {
        id: "page",
        title: "2am - the page fires",
        narration:
          "PagerDuty raises a P1 - kafka_consumer_lag CRITICAL on fraud-decisioning-engine, cluster cards-prod-euw1 - and pages the on-call engineer.",
        nodes: ["pd-alert", "oncall"],
        edges: ["e-alert-oncall"],
      },
      TRIGGER_STEP,
      {
        id: "triage",
        title: "Triage the page",
        narration:
          "First delegation: triage_agent pulls the incident from the PagerDuty MCP and reduces it to hard facts - cluster cards-prod-euw1, consumer group fraud-decisioning-engine, service fraud-decisioning-svc, severity P1.",
        nodes: ["supervisor", "triage", "mcp-pagerduty", "gateway", "anthropic"],
        edges: ["e-sup-triage", "e-triage-pd", "e-agents-gateway", "e-gw-anthropic"],
      },
      {
        id: "lag",
        title: "Diagnosis I - chase the lag",
        badge: "kafka-consumer-lag",
        narration:
          "kafka_diagnosis_agent loads the kafka-consumer-lag skill and goes to the live cluster through Lenses: consumer groups, offsets, topic health. Lag on fraud-decisioning-engine is climbing while the broker itself is healthy and records keep arriving on the topic.",
        nodes: [
          "supervisor",
          "diagnosis",
          "skills",
          "mcp-lenses",
          "lenses-hq",
          "agent-prod",
          "kafka-prod",
          "fraud",
          "gateway",
          "anthropic",
        ],
        edges: [
          "e-sup-diagnosis",
          "e-diagnosis-skills",
          "e-diagnosis-lenses",
          "e-lenses-hq",
          "e-hq-aprod",
          "e-aprod-prod",
          "e-agents-gateway",
          "e-gw-anthropic",
        ],
      },
      {
        id: "schema",
        title: "Diagnosis II - find the schema",
        badge: "kafka-schema-review",
        narration:
          "Stuck offsets on a healthy broker point at deserialization. The agent loads kafka-schema-review, diffs v2 against v1 - amount string vs int, country missing - and calls the root cause: an incompatible schema registered on prod.",
        nodes: [
          "supervisor",
          "diagnosis",
          "skills",
          "mcp-lenses",
          "lenses-hq",
          "agent-prod",
          "kafka-prod",
          "gateway",
          "anthropic",
        ],
        edges: [
          "e-sup-diagnosis",
          "e-diagnosis-skills",
          "e-diagnosis-lenses",
          "e-lenses-hq",
          "e-hq-aprod",
          "e-aprod-prod",
          "e-agents-gateway",
          "e-gw-anthropic",
        ],
      },
      {
        id: "hunt",
        title: "Forensics - hunt the PR",
        narration:
          "code_forensics_agent asks GitHub what merged across dss26-org in the window, code-searches the org for the failing topic, rules out the tempting consumer-config PR in the paged service, and confirms from the diff that the merchant-gateway PR introduced exactly the v2 schema and the NONE compatibility Lenses shows.",
        nodes: ["supervisor", "forensics", "mcp-github", "gh-repo", "gateway", "anthropic"],
        edges: [
          "e-sup-forensics",
          "e-forensics-github",
          "e-github-repo",
          "e-agents-gateway",
          "e-gw-anthropic",
        ],
      },
      {
        id: "report",
        title: "Reporter - write it up",
        badge: "kafka-incident-report",
        narration:
          "reporter_agent loads the kafka-incident-report skill to structure the write-up, publishes the blameless RCA to Confluence, and posts the summary to #sre-oncall: what broke, why, and the next step - revert the merchant-gateway PR and restore the v1-compatible schema.",
        nodes: [
          "supervisor",
          "reporter",
          "skills",
          "mcp-confluence",
          "mcp-slack",
          "rca-page",
          "slack-msg",
          "gateway",
          "anthropic",
        ],
        edges: [
          "e-sup-reporter",
          "e-reporter-skills",
          "e-reporter-confluence",
          "e-reporter-slack",
          "e-confluence-rca",
          "e-slack-msg",
          "e-agents-gateway",
          "e-gw-anthropic",
        ],
      },
      {
        id: "done",
        title: "Back to the human",
        narration:
          "By the time the on-call engineer sits down, the Slack summary and the blameless RCA are already waiting - root cause named, rollback recommended. From page to write-up: a couple of minutes, no human in the loop.",
        nodes: ["rca-page", "slack-msg", "oncall"],
        edges: ["e-rca-oncall", "e-slack-oncall"],
      },
    ],
  },
}

export const DEFAULT_SCENARIO_ID = "consumer-lag"
