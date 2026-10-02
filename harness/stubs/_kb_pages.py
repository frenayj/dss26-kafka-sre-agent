"""The Cards Platform knowledge base, as data.

The Confluence MCP server serves these pages to ``search_pages`` /
``get_page`` in stub mode. The same pages were also written into a real
Confluence space (DSS26), so live mode reads the same content and stub links
point at real page ids.

The world is DSS26 Bank's Cards Platform team - the owners of the Kafka estate
the demo incident happens on. Every name here (clusters, topics, consumer
groups, repos, people) matches the fixtures and the live demo cluster, so a
page the agent reads agrees or disagrees with what Lenses shows for a reason,
never by accident.

Some pages are stale ON PURPOSE (``role="stale"``): relevant to an incident,
found by an obvious search, and wrong in a way the live system or a newer page
exposes. ``planted`` records what is stale and what the agent should conclude.
It is metadata for the brief and the tests - it is never served to the agent,
which has to work it out from the page's own words and its review date.

Dates: the culprit PR merges in dss26-org on the day of the demo (the induce
script merges it minutes before the incident; see harness/github_org/), so
every page is last reviewed well BEFORE that. A note written "after" the
change it explains would give the game away.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# The real space these pages were written into: stub links open the real page,
# and an alert's runbook link resolves the same way in stub and live mode.
SPACE_KEY = "DSS26"
SITE_URL = "https://landoop.atlassian.net/wiki"

# Page ids in that space, by title. A page missing here (added to the
# catalogue but not yet written) gets a stable made-up id instead.
PAGE_IDS: Dict[str, str] = {
    "Cards Platform Engineering": "3979575483",
    "Team charter and ownership map": "3978526723",
    "On-call rotation and escalation": "3979935745",
    "Onboarding: your first two weeks on Cards Platform": "3980001281",
    "Glossary: card payment terms": "3980099585",
    "Cards authorisation flow, end to end": "3978493956",
    "Kafka platform overview: clusters, environments and tooling": "3979968534",
    "ADR-0007: Avro and Schema Registry for card events": "3980034049",
    "ADR-0011: Rename fraud-scoring to fraud-decisioning": "3979247620",
    "Service: fraud-decisioning-svc": "3979968513",
    "Service: merchant-gateway": "3979935766",
    "Topic catalogue and naming conventions": "3979935787",
    "Schema evolution policy for card events": "3980066817",
    "Change management for Kafka changes (CAB)": "3979411458",
    "PCI DSS: handling card data in Kafka": "3978559492",
    "Access to Kafka and Lenses: service accounts and roles": "3979968555",
    "Runbook: Consumer lag critical": "3979280388",
    "Runbook: Roll back an incompatible schema version": "3979575529",
    "Runbook: DLQ triage and reprocessing": "3978854403",
    "Runbook: Under-replicated partitions": "3978690566",
    "Runbook: Consumer group rebalance storms": "3980165121",
    "Incident reports": "3978985479",
    "Postmortem template": "3979247662",
    "INC-2025-03-18-002: fraud-decisioning lag during a rebalance storm": "3980263426",
    "INC-2024-09-12-003: Incompatible schema on cards.clearing.matched.v1": "3980001323",
    "Ops review 2026-04-29": "3978493977",
    "Ops review 2026-04-15": "3980197889",
    "[Archived] On-prem Kafka (kafka-dc1) migration plan": "3979247641",
    "[Archived] Batch fraud scoring runbook": "3979739138",
}
# The "Incident reports" section page: RCAs are filed under it.
INCIDENT_REPORTS_PAGE_ID = "3978985479"

# Section names, in the order the space's page tree shows them.
HOME = "Home"
TEAM = "Team and ways of working"
ARCH = "Architecture and decisions"
SERVICES = "Services and data products"
STANDARDS = "Standards and controls"
RUNBOOKS = "Runbooks"
INCIDENTS = "Incident reports"
NOTES = "Meeting notes"
ARCHIVE = "Archive"


def title_slug(title: str) -> str:
    """The title part of a Confluence page URL: punctuation dropped, spaces as +.

    Cosmetic - Confluence resolves a page by its id - but it makes the link
    look like a real one.
    """
    return re.sub(r"\s+", "+", re.sub(r"[^\w\s.-]", "", title).strip())


@dataclass(frozen=True)
class Planted:
    """What a deliberately stale or misleading page gets wrong (brief only)."""

    stale: str
    truth: str
    shows_in: str
    conclusion: str


@dataclass(frozen=True)
class KbPage:
    slug: str
    title: str
    section: str
    owner: str
    reviewed: str  # YYYY-MM-DD, the "Last reviewed" page property
    labels: Tuple[str, ...]
    summary: str  # 1-2 lines: the brief's description and the search excerpt
    points: Tuple[str, ...] = ()  # what the page says - the writers expand these
    role: str = ""  # "" | "stale" | "red-herring" | "evidence" | "linked-from-alert"
    aliases: Tuple[str, ...] = ()  # URL paths that resolve here (alert runbook links)
    planted: Optional[Planted] = field(default=None, compare=False)

    @property
    def page_id(self) -> str:
        # The real page's id; else stable across edits and re-orderings,
        # derived from the slug alone.
        return PAGE_IDS.get(self.title) or str(1_000_000 + zlib.crc32(self.slug.encode()) % 9_000_000)

    @property
    def url(self) -> str:
        return f"{SITE_URL}/spaces/{SPACE_KEY}/pages/{self.page_id}/{title_slug(self.title)}"

    def body(self) -> str:
        """The page as the agent reads it: page properties, then content."""
        lines = [
            f"# {self.title}",
            "",
            f"Owner: {self.owner} | Last reviewed: {self.reviewed} | "
            f"Labels: {', '.join(self.labels)}",
            "",
            self.summary,
        ]
        if self.points:
            lines.append("")
            lines.extend(f"- {p}" for p in self.points)
        return "\n".join(lines)


PAGES: Tuple[KbPage, ...] = (
    # ------------------------------------------------------------------ home
    KbPage(
        "home", "Cards Platform Engineering", HOME, "lena.fischer", "2026-04-02",
        ("team-home", "cards-platform"),
        "Space home: what the Cards Platform team owns, how to reach us, and "
        "where the runbooks, standards and incident reports live.",
        (
            "We own card authorisation, fraud decisioning and ledger posting on "
            "the cards Kafka cluster (cards-prod-euw1).",
            "On-call is paged through PagerDuty; Slack #cards-platform for "
            "everything else, #sre-oncall during incidents.",
        ),
    ),
    # ------------------------------------------------------------------ team
    KbPage(
        "team-charter", "Team charter and ownership map", TEAM, "lena.fischer",
        "2026-01-20", ("team", "ownership", "raci"),
        "Who owns which service and topic, with a RACI for changes to Tier-1 "
        "card flows.",
        (
            "fraud-decisioning-svc: alex.chen (lead), priya.r, jordan.k.",
            "Kafka platform tooling and Kafka Connect: dana.v (lead), sam.okafor.",
            "Compliance partner for SOX and PCI DSS: claire.martin.",
        ),
    ),
    KbPage(
        "oncall", "On-call rotation and escalation", TEAM, "tomasz.nowak",
        "2024-06-11", ("on-call", "escalation"),
        "Weekly primary/secondary rotation, handover checklist, and who to "
        "escalate to when a Tier-1 alert is not acknowledged.",
        (
            "Alerts page the primary through Opsgenie; unacknowledged after 15 "
            "minutes they go to the secondary.",
            "Escalation contact for Kafka platform issues: tomasz.nowak (SRE lead).",
            "Handover every Monday 10:00 CET in #cards-platform.",
        ),
        role="stale",
        planted=Planted(
            stale="Paging through Opsgenie; escalate to tomasz.nowak.",
            truth="Paging moved to PagerDuty in 2025 and tomasz.nowak left the "
            "bank in February 2025.",
            shows_in="The incident itself arrives from PagerDuty with its own "
            "escalation policy.",
            conclusion="Use the incident's PagerDuty escalation policy, not this "
            "page; list the page as outdated.",
        ),
    ),
    KbPage(
        "onboarding", "Onboarding: your first two weeks on Cards Platform", TEAM,
        "lena.fischer", "2025-09-15", ("onboarding",),
        "Access requests, the systems to learn first, and a starter task list "
        "for new engineers.",
        (
            "Request the cards-platform-engineers SSO group for Lenses read access.",
            "Read the authorisation flow and the schema policy before your first "
            "change to a card event.",
        ),
    ),
    KbPage(
        "glossary", "Glossary: card payment terms", TEAM, "priya.r", "2023-05-08",
        ("glossary",),
        "Authorisation, capture, clearing, settlement, interchange, chargeback "
        "and refund, as the cards topics use them.",
        (
            "Old but still accurate: the domain terms have not changed.",
        ),
    ),
    # ---------------------------------------------------------- architecture
    KbPage(
        "auth-flow", "Cards authorisation flow, end to end", ARCH, "alex.chen",
        "2025-06-30", ("architecture", "authorisation", "tier-1"),
        "How an authorisation request travels from the merchant gateway through "
        "fraud decisioning to the ledger.",
        (
            "merchant-gateway produces cards.authorisation.requested.v1 (Avro).",
            "fraud-decisioning-svc consumes it as consumer group "
            "fraud-decisioning-engine and produces cards.ledger.posted.v1.",
            "If fraud decisioning stops consuming, ledger postings stop too - "
            "lag on the auth topic means a gap in the ledger.",
        ),
    ),
    KbPage(
        "kafka-platform", "Kafka platform overview: clusters, environments and tooling",
        ARCH, "dana.v", "2025-10-14", ("kafka", "platform"),
        "The cards cluster, its Schema Registry and Connect worker, "
        "and the tools we operate them with.",
        (
            "cards-prod-euw1 (production), with its own Schema Registry and "
            "Kafka Connect worker. Pre-production environments are not "
            "managed through Lenses.",
            "Lenses is the console and the MCP endpoint for agents; Confluent "
            "Control Center was retired in January 2025.",
            "Metrics and alerting in Datadog (EU site); alerts route to PagerDuty.",
        ),
    ),
    KbPage(
        "adr-0007", "ADR-0007: Avro and Schema Registry for card events", ARCH,
        "priya.r", "2022-03-09", ("adr", "schema", "avro"),
        "Decision to serialise every card event as Avro with schemas in Schema "
        "Registry, one subject per topic value.",
        (
            "Status: Accepted. Producers register schemas; consumers deserialise "
            "with the registry.",
            "Compatibility is configured per subject.",
        ),
    ),
    KbPage(
        "adr-0011", "ADR-0011: Rename fraud-scoring to fraud-decisioning", ARCH,
        "alex.chen", "2024-05-21", ("adr", "fraud-decisioning"),
        "Decision to rename the fraud-scoring service and its consumer group "
        "when it took over approve/decline decisions.",
        (
            "Status: Accepted, completed 2024-06.",
            "Service fraud-scoring became fraud-decisioning-svc; consumer group "
            "fraud-scoring-consumer was replaced by fraud-decisioning-engine and "
            "deleted.",
        ),
        role="evidence",
    ),
    # -------------------------------------------------------------- services
    KbPage(
        "svc-fraud-decisioning", "Service: fraud-decisioning-svc", SERVICES,
        "alex.chen", "2026-03-03", ("service", "fraud-decisioning", "tier-1"),
        "The Tier-1 service that approves or declines card authorisations and "
        "posts the result to the ledger.",
        (
            "Repo: dss26-org/fraud-decisioning-svc. Consumer group: "
            "fraud-decisioning-engine on cards-prod-euw1.",
            "Consumes cards.authorisation.requested.v1, produces "
            "cards.ledger.posted.v1.",
            "Deserialises with the Schema Registry; a record it cannot read stops "
            "the partition until the schema is fixed.",
            "Lag monitor: kafka_consumer_lag in Datadog, critical above 5,000.",
        ),
    ),
    KbPage(
        "svc-merchant-gateway", "Service: merchant-gateway", SERVICES,
        "payments-edge team", "2025-11-19", ("service", "producer"),
        "The edge service that turns merchant authorisation requests into "
        "cards.authorisation.requested.v1 events.",
        (
            "Owned by the payments-edge team; registers the producer schema for "
            "cards.authorisation.requested.v1.",
        ),
    ),
    KbPage(
        "topic-catalogue", "Topic catalogue and naming conventions", SERVICES,
        "priya.r", "2026-02-10", ("topics", "naming", "catalogue"),
        "All 32 cards topics with owner, tier, data classification, and the "
        "naming rule they follow.",
        (
            "Names follow <domain>.<entity>.<event>.v<N>, e.g. "
            "cards.authorisation.requested.v1.",
            "Tags record owner, criticality, compliance scope, PII level and EU "
            "data residency.",
        ),
    ),
    # ------------------------------------------------------------- standards
    KbPage(
        "schema-policy", "Schema evolution policy for card events", STANDARDS,
        "priya.r", "2023-02-14", ("standard", "schema", "avro", "compatibility"),
        "Rules for changing an Avro schema on a cards topic without breaking "
        "consumers.",
        (
            "Every cards.* subject is BACKWARD compatible; the setting is never "
            "changed per subject.",
            "The schema-compat CI check runs on every pull request and blocks "
            "incompatible changes before merge, so an incompatible version "
            "cannot reach the registry.",
            "Type changes (for example double to string) need a new topic "
            "version.",
        ),
        role="stale",
        planted=Planted(
            stale="The CI check blocks every incompatible change, so a breaking "
            "version cannot reach the registry; compatibility is never changed "
            "per subject.",
            truth="The schema-compat CI job has been disabled since 2026-04-15 "
            "(CARDS-1423), and the subject's compatibility was set to NONE.",
            shows_in="Ops review 2026-04-15 note; the subject config in Schema "
            "Registry via Lenses.",
            conclusion="The guardrail the policy relies on was off. Recommend "
            "re-enabling the CI check and locking subject compatibility; flag the "
            "policy as outdated.",
        ),
    ),
    KbPage(
        "change-management", "Change management for Kafka changes (CAB)", STANDARDS,
        "lena.fischer", "2025-04-22", ("standard", "change-management", "cab"),
        "Which Kafka changes are standard changes and which need a CAB ticket.",
        (
            "A schema change on a Tier-1 topic is a normal change: CAB ticket and "
            "a named approver.",
            "New topics and ACL grants on Tier-2 topics are standard changes.",
        ),
    ),
    KbPage(
        "pci-dss", "PCI DSS: handling card data in Kafka", STANDARDS,
        "claire.martin", "2025-07-03", ("standard", "pci-dss", "data-classification"),
        "What card data may appear in topics, logs and tickets.",
        (
            "Topics carry card_token, never a PAN.",
            "Lenses masks sensitive fields; never paste message payloads into "
            "tickets or Slack.",
        ),
    ),
    KbPage(
        "access", "Access to Kafka and Lenses: service accounts and roles",
        STANDARDS, "dana.v", "2025-12-09", ("access", "lenses", "service-accounts"),
        "How people and services get access to the cards cluster.",
        (
            "People: SSO groups mapped to Lenses roles; write access is "
            "time-boxed and approved.",
            "Services: one service account each. svc-sre-agent is read-only "
            "(added 2025-12).",
        ),
    ),
    # -------------------------------------------------------------- runbooks
    KbPage(
        "rb-consumer-lag", "Runbook: Consumer lag critical", RUNBOOKS,
        "tomasz.nowak", "2024-03-12", ("runbook", "consumer-lag", "fraud-scoring"),
        "First response when the consumer lag alert fires on the fraud scoring "
        "consumer.",
        (
            "Check the fraud-scoring-consumer group in Grafana (Kafka / Consumers "
            "dashboard).",
            "Lag is almost always throughput: scale fraud-scoring to 6 replicas "
            "and restart the pods.",
            "If lag is still above 10,000 after 15 minutes, escalate to the SRE "
            "lead.",
            "Last resort: skip past a bad record with kafka-consumer-groups "
            "--reset-offsets --shift-by 1.",
        ),
        role="stale",
        aliases=("Runbooks/Consumer-Lag-Critical",),
        planted=Planted(
            stale="Consumer group fraud-scoring-consumer; dashboards in Grafana; "
            "scale out and restart; 10,000 threshold.",
            truth="The group is fraud-decisioning-engine since ADR-0011; monitoring "
            "is Datadog; the monitor fires at 5,000; a record that cannot be "
            "deserialised does not clear by scaling.",
            shows_in="The alert payload (Datadog, 5,000); Lenses consumer group "
            "and its stuck offset; ADR-0011.",
            conclusion="Do not follow the scale-out step for a deserialisation "
            "failure; the runbook predates the rename and the Datadog move. List "
            "it as outdated.",
        ),
    ),
    KbPage(
        "rb-schema-rollback", "Runbook: Roll back an incompatible schema version",
        RUNBOOKS, "priya.r", "2024-10-02", ("runbook", "schema", "rollback"),
        "Restore consumers after an incompatible schema version was registered.",
        (
            "Soft-delete the incompatible version of the subject, restore "
            "BACKWARD compatibility, then restart the consumer from its committed "
            "offset.",
            "Do it in Confluent Control Center: Topics > Schema > Version history.",
        ),
        role="stale",
        planted=Planted(
            stale="The UI steps use Confluent Control Center.",
            truth="Control Center was retired in January 2025; Lenses is the "
            "console. The procedure itself is still right.",
            shows_in="Kafka platform overview page.",
            conclusion="Cite the procedure as the remediation, and flag the UI "
            "steps as outdated.",
        ),
    ),
    KbPage(
        "rb-dlq", "Runbook: DLQ triage and reprocessing", RUNBOOKS, "sam.okafor",
        "2025-10-21", ("runbook", "dlq", "kafka-connect"),
        "Read the failure headers on a connector's dead-letter queue and replay "
        "the fixed records.",
        (
            "Failure reason, partition and offset are in the record headers "
            "(errors.deadletterqueue.context.headers.enable=true).",
        ),
    ),
    KbPage(
        "rb-urp", "Runbook: Under-replicated partitions", RUNBOOKS, "dana.v",
        "2025-05-13", ("runbook", "broker", "replication"),
        "What to check when partitions fall out of sync on a cards broker.",
    ),
    KbPage(
        "rb-rebalance", "Runbook: Consumer group rebalance storms", RUNBOOKS,
        "jordan.k", "2025-03-25", ("runbook", "consumer-group", "rebalance"),
        "Spot and stop a consumer group that keeps rebalancing.",
        (
            "Symptom: lag rising across all partitions while members join and "
            "leave every few minutes.",
            "Usual cause: max.poll.interval.ms too low for slow batches or GC "
            "pauses.",
        ),
    ),
    # ------------------------------------------------------------- incidents
    KbPage(
        "incidents-index", "Incident reports", INCIDENTS, "lena.fischer",
        "2026-04-30", ("postmortem", "index"),
        "Index of every postmortem, newest first. New RCAs are filed under this "
        "page.",
    ),
    KbPage(
        "pm-template", "Postmortem template", INCIDENTS, "lena.fischer",
        "2025-06-02", ("postmortem", "template"),
        "The blameless template every incident report starts from.",
        (
            "Title format: INC-YYYY-MM-DD-### - short description.",
            "Sections: TL;DR, impact, timeline, root cause, actions, related pages.",
        ),
    ),
    KbPage(
        "inc-2025-03-18-002",
        "INC-2025-03-18-002: fraud-decisioning lag during a rebalance storm",
        INCIDENTS, "jordan.k", "2025-03-25",
        ("postmortem", "consumer-lag", "fraud-decisioning"),
        "fraud-decisioning-engine lag peaked at 210,000 while the group "
        "rebalanced every few minutes.",
        (
            "Cause: max.poll.interval.ms too low after a GC change; members kept "
            "timing out.",
            "Fix: raised max.poll.interval.ms, tuned GC.",
        ),
        role="red-herring",
        planted=Planted(
            stale="Same consumer group, same lag alert - caused by rebalances.",
            truth="This time membership is stable and one partition is stuck at a "
            "fixed offset with deserialisation errors.",
            shows_in="Lenses consumer group members and per-partition offsets.",
            conclusion="Similar symptom, different cause: cite it as ruled out.",
        ),
    ),
    KbPage(
        "inc-2024-09-12-003",
        "INC-2024-09-12-003: Incompatible schema on cards.clearing.matched.v1",
        INCIDENTS, "priya.r", "2024-09-20", ("postmortem", "schema", "avro"),
        "A producer registered a schema that dropped a required field and the "
        "clearing consumers stopped.",
        (
            "Root cause: incompatible schema registered without review.",
            "Action item: add a schema-compat check to CI for every cards repo. "
            "Status: Done (2024-10).",
        ),
        role="evidence",
    ),
    # ----------------------------------------------------------------- notes
    KbPage(
        "ops-2026-04-29", "Ops review 2026-04-29", NOTES, "lena.fischer",
        "2026-04-29", ("meeting-notes", "ops-review"),
        "Weekly ops review: SLOs, open actions, upcoming changes.",
        (
            "Planned: cards.authorisation.requested.v1 amount as a decimal string "
            "(v2). Order agreed: upgrade the fraud-decisioning consumer first, "
            "then change the producer schema. Owner alex.chen.",
            "CARDS-1423 (re-enable schema-compat CI) still open.",
        ),
        role="evidence",
    ),
    KbPage(
        "ops-2026-04-15", "Ops review 2026-04-15", NOTES, "lena.fischer",
        "2026-04-15", ("meeting-notes", "ops-review"),
        "Weekly ops review: CI reliability, Connect worker upgrade, on-call "
        "handover.",
        (
            "schema-compat CI job disabled temporarily: the Schema Registry "
            "container in CI is flaky. CARDS-1423 to re-enable, owner jordan.k.",
        ),
        role="evidence",
    ),
    # --------------------------------------------------------------- archive
    KbPage(
        "arch-kafka-dc1", "[Archived] On-prem Kafka (kafka-dc1) migration plan",
        ARCHIVE, "tomasz.nowak", "2022-11-30", ("archived", "migration"),
        "The 2022 plan to move the cards topics from the on-prem kafka-dc1 "
        "cluster to cards-prod-euw1.",
    ),
    KbPage(
        "arch-batch-fraud", "[Archived] Batch fraud scoring runbook", ARCHIVE,
        "tomasz.nowak", "2021-06-14", ("archived", "runbook", "fraud-scoring"),
        "Runbook for the nightly batch fraud scoring job that streaming fraud "
        "decisioning replaced.",
    ),
)


BY_ID: Dict[str, KbPage] = {p.page_id: p for p in PAGES}
BY_SLUG: Dict[str, KbPage] = {p.slug: p for p in PAGES}

assert len(BY_ID) == len(PAGES), "page id collision - rename a slug"
