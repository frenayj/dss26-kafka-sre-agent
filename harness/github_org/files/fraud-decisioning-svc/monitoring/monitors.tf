# Monitors that page for fraud-decisioning-svc. The PagerDuty service is
# PSVC42A (escalation policy "Cards Platform - Primary").

locals {
  runbook_consumer_lag = "https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3979280388/Runbook+Consumer+lag+critical"

  lag_tags = [
    "kafka_cluster:cards-prod-euw1",
    "consumer_group:fraud-decisioning-engine",
    "topic:cards.authorisation.requested.v1",
    "service:fraud-decisioning-svc",
    "team:cards-platform",
    "env:prod",
    "region:eu-west-1",
  ]
}

resource "datadog_monitor" "kafka_consumer_lag" {
  name  = "kafka_consumer_lag"
  type  = "query alert"
  query = "avg(last_5m):avg:kafka.consumer_lag{kafka_cluster:cards-prod-euw1,consumer_group:fraud-decisioning-engine,topic:cards.authorisation.requested.v1} by {consumer_group,topic} > 50000"

  message = <<-EOT
    {{#is_alert}}
    {{consumer_group.name}} is {{value}} records behind on {{topic.name}} (cards-prod-euw1).
    Card authorisations are waiting for a decision and ledger postings to
    cards.ledger.posted.v1 are delayed by the same amount.
    Runbook: ${local.runbook_consumer_lag}
    @pagerduty-fraud-decisioning-svc
    {{/is_alert}}
    {{#is_warning}}
    {{consumer_group.name}} lag on {{topic.name}} is {{value}} and rising. @slack-cards-platform
    {{/is_warning}}
    {{#is_recovery}}
    {{consumer_group.name}} has caught up on {{topic.name}}. @pagerduty-fraud-decisioning-svc @slack-cards-platform
    {{/is_recovery}}
  EOT

  monitor_thresholds {
    critical          = 50000
    critical_recovery = 10000
    warning           = 20000
  }

  evaluation_delay    = 60
  require_full_window = false
  notify_no_data      = true
  no_data_timeframe   = 15
  renotify_interval   = 30
  include_tags        = true
  priority            = 1

  tags = local.lag_tags
}
