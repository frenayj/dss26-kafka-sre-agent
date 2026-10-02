"""dss26-org/kafka-platform - topics, subjects, service accounts and ACLs as code.

Story role (schema break):

* Decoy merged the same morning: fatima.benali's prefixed consumer-group grant
  for merchant-analytics-stream v2. It edits ``acls/svc-merchant-analytics.yaml``
  right under that account's READ grant on ``cards.authorisation.requested.v1``,
  so it surfaces in any search for the topic, but it only widens one consumer
  account's group grant. Nothing fraud-decisioning uses changes.
* Evidence in history: the auth subject is declared BACKWARD (priya.r,
  2023-02, after ADR-0007) and ``validate.py`` rejects anything weaker for a
  cards subject - so the NONE on the live subject was not set from here.
  ``svc-sre-agent`` is read-only (dana.v, 2025-12, per the Confluence access
  page).

Topic files are generated from ``scripts/demo_topics.py`` ``TOPICS`` (names,
owners, tiers, descriptions, tags, partitions) so the repo and the live
catalogue cannot drift. History is built by mutating a small model of
the repo (:class:`World`) and diffing each rendered tree against the last one,
so every commit is a minimal, coherent change.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from dataclasses import dataclass, field, replace

from model import (
    DEFAULT_LABELS,
    FILES_ROOT,
    REPO_ROOT,
    Commit,
    Delete,
    Edit,
    Label,
    RepoSpec,
    ScenarioPR,
    Write,
)
from people import TEAMS

sys.path.insert(0, str(REPO_ROOT / "harness" / "seed"))
from demo_topics import TOPICS, TopicSpec, tags_for  # noqa: E402

REPO = "kafka-platform"
F = "kafka-platform"  # files/ subfolder
AUTH = "cards.authorisation.requested.v1"
LEDGER = "cards.ledger.posted.v1"
PARTNER_TOPIC = "cards.partner.settlement.v1"
PARTNER_DLQ = "cards.partner.settlement.v1.dlq"

# The bank's clusters. The demo stack runs only cards-prod-euw1; the repo also
# declares a dev cluster and the on-premises cluster the bank migrated from.
PROD_ENV = "cards-prod-euw1"
DEV_ENV = "cards-dev-euw1"
DC1 = "kafka-dc1"
PROD_ONLY_TOPICS = {LEDGER, PARTNER_TOPIC, PARTNER_DLQ}


def topic_envs(name: str) -> tuple[str, ...]:
    return (PROD_ENV,) if name in PROD_ONLY_TOPICS else (PROD_ENV, DEV_ENV)


def _src(path: str) -> str:
    return (FILES_ROOT / F / path).read_text()


# ---------------------------------------------------------------------------
# Text history helpers: derive earlier versions of a file from its final form
# ---------------------------------------------------------------------------

Pair = tuple[str, str]  # (old, new): applying it forward replaces old by new


def _once(text: str, needle: str) -> None:
    if text.count(needle) != 1:
        raise ValueError(f"expected exactly one {needle[:70]!r}, found {text.count(needle)}")


def def_pair(text: str, name: str) -> Pair:
    """The pair that adds def ``name`` (as it is in ``text``) in front of what follows it."""
    node = next(n for n in ast.walk(ast.parse(text))
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    lines = text.splitlines(keepends=True)
    start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
    end = node.end_lineno
    while end < len(lines) and not lines[end].strip():
        end += 1
    anchor = lines[end]
    block = "".join(lines[start:end])
    _once(text, block + anchor)
    return anchor, block + anchor


def line_pair(text: str, line: str) -> Pair:
    """The pair that adds ``line`` (a whole line of ``text``) after the line before it."""
    lines = text.splitlines(keepends=True)
    i = lines.index(line)
    _once(text, lines[i - 1] + line)
    return lines[i - 1], lines[i - 1] + line


def between_pair(text: str, before: str, after: str) -> Pair:
    """The pair that adds whatever sits between ``before`` and ``after``."""
    _once(text, before)
    start = text.index(before) + len(before)
    end = text.index(after, start)
    return before + after, text[text.index(before):end] + after


class Versions:
    """A file's history as named steps, rewound from its final text.

    ``steps`` is chronological; each step is a list of callables that, given
    the text *after* that step, return the pair that step applied. Rewinding
    walks the steps backwards to the first version; ``at(step)`` replays them.
    """

    def __init__(self, final: str, steps: list[tuple[str, list]]):
        self.final = final
        self.pairs: dict[str, list[Pair]] = {}
        text = final
        for name, makers in reversed(steps):
            pairs: list[Pair] = []
            for make in reversed(makers):
                old, new = make(text) if callable(make) else make
                _once(text, new)
                text = text.replace(new, old, 1)
                pairs.append((old, new))
            self.pairs[name] = list(reversed(pairs))
        self.first = text
        self.order = [name for name, _ in steps]

    def at(self, step: str | None) -> str:
        text = self.first
        if step is None:
            return text
        for name in self.order[: self.order.index(step) + 1]:
            for old, new in self.pairs[name]:
                _once(text, old)
                text = text.replace(old, new, 1)
        return text


def _d(name: str):
    return lambda text: def_pair(text, name)


def _l(line: str):
    return lambda text: line_pair(text, line)


# ---------------------------------------------------------------------------
# Static files and their versions
# ---------------------------------------------------------------------------

VALIDATE = Versions(_src("scripts/validate.py"), [
    ("schema", [
        ("owners and clusters, replication settings and service-account ACLs.\n",
         "owners and clusters, replication settings, Schema Registry subjects and\n"
         "compatibility, and service-account ACLs.\n"),
        lambda t: between_pair(t, 'CLEANUP_POLICIES = ("delete", "compact", "compact,delete")\n',
                               "\nCLUSTER_KEYS"),
        _d("check_schema"),
        _l("    check_schema,\n"),
    ]),
    ("tags", [_d("check_tags"), _l("    check_tags,\n")]),
    ("dlq", [_d("check_dead_letter"), _l("    check_dead_letter,\n")]),
    ("wildcard", [
        _l('READ_ONLY = {"READ", "DESCRIBE", "DESCRIBE_CONFIGS"}\n'),
        ('        if pattern == "literal" and name not in declared:\n',
         '        if pattern == "literal" and name != "*" and name not in declared:\n'),
        _d("check_wildcards"),
        _l("    check_wildcards,\n"),
    ]),
])

TOPIC_SAMPLE_TAGS = (
    "tags:\n  - domain:cards\n  - owner:cards-platform\n  - criticality:tier-2\n"
    "  - data-residency:eu\n"
)
TESTS = Versions(_src("tests/test_validate.py"), [
    ("tags", [("  compatibility: BACKWARD\n\"\"\"\n",
               "  compatibility: BACKWARD\n" + TOPIC_SAMPLE_TAGS + "\"\"\"\n"),
              _d("test_tags_agree_with_owner_and_tier")]),
    ("dlq", [_d("test_dead_letter_topic_names_its_source")]),
    ("wildcard", [_d("test_wildcard_grants_are_read_only")]),
])

_README = _src("README.md")
README = Versions(_README, [
    ("dev", [(
        "| `cards-prod-euw1` | production | eu-west-1, brokers spread over three AZs, RF 3 minimum |\n",
        "| `cards-prod-euw1` | production | eu-west-1, brokers spread over three AZs, RF 3 minimum |\n"
        "| `cards-dev-euw1` | development | eu-west-1, RF 3 minimum |\n",
    ), ("  - cards-prod-euw1\n  - kafka-dc1\npartitions",
        "  - cards-prod-euw1\n  - cards-dev-euw1\n  - kafka-dc1\npartitions")]),
    ("dc1-retired", [(
        "| `cards-dev-euw1` | development | eu-west-1, RF 3 minimum |\n"
        "| `kafka-dc1` | production (on-premises) | being retired, see below |\n\n"
        "### kafka-dc1 migration\n\n"
        "The cards topics move from the on-premises `kafka-dc1` cluster to\n"
        "`cards-prod-euw1`. While MirrorMaker 2 replicates, every topic and service\n"
        "account lists both clusters; consumers cut over first, then producers.\n"
        "Plan and status: *On-prem Kafka (kafka-dc1) migration plan* in Confluence.\n"
        "Questions to tomasz.nowak.\n",
        "| `cards-dev-euw1` | development | eu-west-1, RF 3 minimum |\n",
    ), ("  - cards-prod-euw1\n  - cards-dev-euw1\n  - kafka-dc1\npartitions",
        "  - cards-prod-euw1\n  - cards-dev-euw1\npartitions")]),
    ("schema", [
        ("- `cleanup.policy` and `retention.ms` are set;\n",
         "- `cleanup.policy` and `retention.ms` are set;\n"
         "- Avro topics declare their subject as `<name>-value` (one subject per topic,\n"
         "  ADR-0007) and a compatibility level. Cards subjects are `BACKWARD` or\n"
         "  stricter;\n"),
        ("value_format: avro\n```",
         "value_format: avro\nschema:\n  subject: cards.authorisation.requested.v1-value\n"
         "  compatibility: BACKWARD\n```"),
        lambda t: between_pair(t, "different partitions - talk to the consumers of the topic first.\n",
                               "\n## Requesting access"),
    ]),
    ("tests", [("python3 scripts/validate.py\n```", "python3 scripts/validate.py\n"
                "python3 -m unittest discover -s tests\n```"),
               ("1. Open a pull request. `validate` runs the checks.\n",
                "1. Open a pull request. `validate` runs the checks and the unit tests.\n")]),
    ("service-accounts-doc", [
        ("scripts/validate.py            the rules below - runs on every pull request\n",
         "scripts/validate.py            the rules below - runs on every pull request\n"
         "docs/service-accounts.md       principals, credentials and ACL conventions\n"),
        ("Add or edit `acls/svc-<service>.yaml`. The squad",
         "Add or edit `acls/svc-<service>.yaml` (see\n"
         "[docs/service-accounts.md](docs/service-accounts.md)). The squad"),
    ]),
    ("apply", [
        ("by hand: open a pull request here, and a platform engineer applies the\n"
         "merged change to every cluster the file lists.\n",
         "by hand: open a pull request here, and the `apply` workflow makes the cluster\n"
         "match `main`.\n"),
        ("scripts/validate.py            the rules below - runs on every pull request\n",
         "scripts/validate.py            the rules below - runs on every pull request\n"
         "scripts/apply.py               plan / apply one cluster - runs on merge\n"),
        ("3. After merge, the platform on-call applies the change to each cluster in\n"
         "   the file with `kafka-topics`, `kafka-configs` and `kafka-acls`, and\n"
         "   comments on the pull request when it is done.\n"
         "4. Removing a topic or an ACL is a separate change with a PLAT ticket.\n",
         "3. On merge, `apply` plans and applies `cards-dev-euw1`, then\n"
         "   `cards-prod-euw1` once a platform engineer approves the\n"
         "   `cards-prod-euw1` environment. The plan is in the job log.\n"
         "4. `apply` never deletes. Removing a topic or an ACL is a manual change with\n"
         "   a PLAT ticket; until then `apply` lists it as unmanaged.\n"),
    ]),
    ("tags", [
        ("- Avro topics declare their subject as `<name>-value` (one subject per topic,\n"
         "  ADR-0007) and a compatibility level. Cards subjects are `BACKWARD` or\n"
         "  stricter;\n",
         "- Avro topics declare their subject as `<name>-value` (one subject per topic,\n"
         "  ADR-0007) and a compatibility level. Cards subjects are `BACKWARD` or\n"
         "  stricter;\n"
         "- `tags` carry `domain:`, `owner:`, `criticality:` and `data-residency:eu`,\n"
         "  matching the file;\n"),
        ("  compatibility: BACKWARD\n```",
         "  compatibility: BACKWARD\ntags:\n  - domain:cards\n  - owner:cards-platform\n"
         "  - criticality:tier-1\n  - data-residency:eu\n```"),
        lambda t: between_pair(t, "the [DSS26 space](https://landoop.atlassian.net/wiki/spaces/DSS26/overview).\n",
                               "\n## Requesting access"),
    ]),
    ("contacts", [(
        "- Out of hours: Opsgenie team *Kafka Platform*.\n"
        "- Dashboards: Grafana, *Kafka / Cluster overview* and *Kafka / Consumers*.\n",
        "- Out of hours: PagerDuty service *Kafka Platform*, escalation policy\n"
        "  *Platform Engineering - Primary*.\n"
        "- Dashboards: Datadog EU, *Kafka / Cluster overview* and *Kafka / Consumers*.\n",
    )]),
    ("dlq", [(
        "  matching the file;\n",
        "  matching the file;\n"
        "- a dead-letter topic is named `<topic>.dlq`, sets `dead_letter_for` to the\n"
        "  topic it serves and stores raw bytes;\n",
    )]),
    ("wildcard", [(
        "- ACLs only name declared topics and prefixed write grants never cover a\n"
        "  catalogue topic.\n",
        "- ACLs only name declared topics, prefixed write grants never cover a\n"
        "  catalogue topic, and wildcard (`\"*\"`) grants are read-only.\n",
    )]),
])

_DOCS = _src("docs/service-accounts.md")
SA_DOC = Versions(_DOCS, [
    ("transactional", [(
        "  on older clients also need `IDEMPOTENT_WRITE` on `kafka-cluster`.\n",
        "  on older clients also need `IDEMPOTENT_WRITE` on `kafka-cluster`.\n"
        "- Exactly-once Kafka Streams applications also need `WRITE` and `DESCRIBE` on\n"
        "  `transactional_id`, prefixed with the `application.id`.\n",
    )]),
    ("connect", [lambda t: between_pair(t, "is `User:svc-<service>`.\n", "\n## Credentials")]),
    ("read-only", [lambda t: between_pair(t, "a rollout, use a prefixed group grant rather than sharing a group.\n",
                                          "\n## Removing access")]),
    ("rotation", [("Rotation is every 90 days", "Rotation is every 60 days")]),
])

WF_VALIDATE = Versions(_src(".github/workflows/validate.yml"), [
    ("tests", [("        run: python scripts/validate.py\n",
                "        run: python scripts/validate.py\n"
                "      - name: Unit tests\n"
                "        run: python -m unittest discover -s tests -v\n")]),
    ("checkout-v4", [("actions/checkout@v3", "actions/checkout@v4")]),
    ("setup-python-v5", [("actions/setup-python@v4", "actions/setup-python@v5")]),
    ("py312", [('python-version: "3.10"', 'python-version: "3.12"')]),
    ("checkout-v5", [("actions/checkout@v4", "actions/checkout@v5")]),
    ("setup-python-v6", [("actions/setup-python@v5", "actions/setup-python@v6")]),
])
_WF_APPLY = _src(".github/workflows/apply.yml")


def wf_apply(checkout: str) -> str:
    assert _WF_APPLY.count("actions/checkout@v5") == 2
    return _WF_APPLY.replace("actions/checkout@v5", f"actions/checkout@{checkout}")


def _requirements(pyyaml: str, confluent: str | None = None) -> str:
    out = f"# scripts/validate.py\nPyYAML=={pyyaml}\n"
    if confluent:
        out += f"# scripts/apply.py\nconfluent-kafka=={confluent}\n"
    return out


CATALOG_INFO = """\
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: kafka-platform
  title: Kafka platform as code (cards clusters)
  description: Topics, Schema Registry subjects, service accounts and ACLs for the cards Kafka clusters.
  annotations:
    github.com/project-slug: dss26-org/kafka-platform
  tags: [kafka, gitops, schema-registry, acl]
  links:
    - url: https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3979968534/Kafka+platform+overview+clusters+environments+and+tooling
      title: Kafka platform overview
    - url: https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3979935787/Topic+catalogue+and+naming+conventions
      title: Topic catalogue and naming conventions
    - url: https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980034049/ADR-0007+Avro+and+Schema+Registry+for+card+events
      title: ADR-0007 - Avro and Schema Registry for card events
spec:
  type: configuration
  lifecycle: production
  owner: group:platform-engineering
  system: cards-kafka-platform
"""

PR_TEMPLATE = """\
## What

## Why

## Impact
<!-- Which topics and service accounts change, on which clusters. -->

## Checklist
- [ ] `python3 scripts/validate.py` passes locally
- [ ] The owning squad has reviewed (CODEOWNERS)
- [ ] New write access to a tier-1 topic in production: CHG ticket linked
"""

GITIGNORE = "__pycache__/\n*.pyc\n.venv/\n"


def _teams_yaml() -> str:
    lines = [
        "# Squads that can own a topic or a service account. Mirrors the GitHub",
        "# teams in dss26-org (tribe = parent team).",
        "teams:",
    ]
    for team in TEAMS:
        if team.parent is None:
            continue
        lines += [f"  - slug: {team.slug}", f"    name: {team.name}",
                  f"    tribe: {team.parent}", f'    slack: "#{team.slug}"']
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

CLUSTERS = {
    PROD_ENV: dict(environment="production", region="eu-west-1",
                   bootstrap="demo-kafka-prod:9092", registry="http://demo-kafka-prod:8081"),
    DEV_ENV: dict(environment="development", region="eu-west-1",
                  bootstrap="demo-kafka-dev:9092", registry="http://demo-kafka-dev:8081"),
    DC1: dict(environment="production", region="on-premises (Paris DC1)",
              bootstrap=",".join(f"kafka-dc1-0{i}.dss26.internal:9093" for i in (1, 2, 3)),
              registry="https://schema-registry.dc1.dss26.internal:8081"),
}


def render_cluster(name: str, console: str) -> str:
    c = CLUSTERS[name]
    return "\n".join([
        f"name: {name}",
        f"environment: {c['environment']}",
        f"region: {c['region']}",
        f"bootstrap_servers: {c['bootstrap']}",
        f"schema_registry_url: {c['registry']}",
        "security_protocol: SASL_SSL",
        "sasl_mechanism: SCRAM-SHA-512",
        "min_replication_factor: 3",
        "# Broker super.users, set by the broker provisioning. Listed here so the",
        "# quarterly access review sees every principal in one place.",
        "super_users:",
        "  - User:svc-kafka-admin",
        f"  - User:{console}",
    ]) + "\n"


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

DAY_MS = 86_400_000

PARTNER = TopicSpec(
    name=PARTNER_TOPIC,
    description=(
        "Settlement postings from partner acquirer banks as schemaless JSON. "
        "Partners drop hand-built files on SFTP and partner-settlement-ingest "
        "publishes them record by record. Loaded into the settlement database by sink-jdbc-partner-settlement; records "
        "the sink cannot parse go to cards.partner.settlement.v1.dlq. Production only."
    ),
    tags=tags_for(domain="cards", owner="cards-platform", criticality="tier-2",
                  compliance=("sox",), pii="none", event_type="partner-settlement"),
    partitions=3,
)
PARTNER_DLQ_SPEC = TopicSpec(
    name=PARTNER_DLQ,
    description=(
        "Dead-letter queue for sink-jdbc-partner-settlement. Holds the original "
        "record bytes; the failure reason and the source topic, partition and "
        "offset are in the record headers. Triage and replay: DLQ runbook in the "
        "DSS26 space."
    ),
    tags=tags_for(domain="cards", owner="cards-platform", criticality="tier-2",
                  compliance=("sox",), pii="none", event_type="dead-letter",
                  extras=(f"upstream:{PARTNER_TOPIC}",)),
    partitions=1,
)

SPECS: dict[str, TopicSpec] = {t.name: t for t in (*TOPICS, PARTNER, PARTNER_DLQ_SPEC)}
VALUE_FORMAT = {PARTNER_TOPIC: "json", PARTNER_DLQ: "bytes"}

RETENTION_DAYS = (  # first matching prefix wins
    (LEDGER, 30), ("ledger.", 30), ("cards.authorisation.", 7),
    ("cards.clearing.", 30), ("cards.settlement.", 30), ("cards.interchange.", 30),
    ("cards.chargeback.", 30), ("cards.refund.", 14), ("cards.card.", 14),
    ("cards.statement.", 7), (PARTNER_DLQ, 14), (PARTNER_TOPIC, 7),
    ("customer.", 7), ("fraud.score.", 7), ("fraud.case.", 30), ("risk.", 14),
    ("aml.", 30), ("sanctions.", 30), ("kyc.", 30),
)


def _tag(spec: TopicSpec, key: str) -> str:
    return next(t.split(":", 1)[1] for t in spec.tags if t.startswith(f"{key}:"))


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(text, width=74, initial_indent="  ", subsequent_indent="  ",
                         break_on_hyphens=False)


def topic_path(name: str) -> str:
    return f"topics/{name.split('.')[0]}/{name}.yaml"


def render_topic(spec: TopicSpec, clusters: list[str], *, schema: bool, tags: bool) -> str:
    days = next(d for prefix, d in RETENTION_DAYS if spec.name.startswith(prefix))
    fmt = VALUE_FORMAT.get(spec.name, "avro")
    lines = [
        f"name: {spec.name}",
        f"owner: {_tag(spec, 'owner')}",
        f"tier: {_tag(spec, 'criticality')}",
        "description: >-",
        *_wrap(spec.description),
        "clusters:",
        *(f"  - {c}" for c in clusters),
        f"partitions: {spec.partitions}",
        "replication_factor: 3",
        "config:",
        "  cleanup.policy: delete",
        f"  retention.ms: {days * DAY_MS}  # {days} days",
        "  min.insync.replicas: 2",
        f"value_format: {fmt}",
    ]
    if spec.name.endswith(".dlq"):
        lines.append(f"dead_letter_for: {spec.name.removesuffix('.dlq')}")
    if schema and fmt == "avro":
        lines += ["schema:", f"  subject: {spec.name}-value", "  compatibility: BACKWARD"]
    if tags:
        lines += ["tags:", *(f"  - {t}" for t in spec.tags)]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Service accounts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Grant:
    resource: str
    name: str
    ops: tuple[str, ...]
    pattern: str = "literal"
    comment: str = ""


@dataclass(frozen=True)
class Account:
    name: str
    owner: str
    description: str
    grants: tuple[Grant, ...]
    envs: tuple[str, ...] = (PROD_ENV, DEV_ENV)


def topic(name: str, *ops: str, pattern: str = "literal", comment: str = "") -> Grant:
    return Grant("topic", name, ops, pattern, comment)


def group(name: str, *ops: str, pattern: str = "literal", comment: str = "") -> Grant:
    return Grant("group", name, ops or ("READ",), pattern, comment)


R, W = ("READ", "DESCRIBE"), ("WRITE", "DESCRIBE")


def render_account(acc: Account, clusters: list[str]) -> str:
    lines = [f"service_account: {acc.name}", f"owner: {acc.owner}", "description: >-",
             *_wrap(acc.description), "clusters:", *(f"  - {c}" for c in clusters), "acls:"]
    for g in acc.grants:
        lines += [f"  # {c}" for c in g.comment.splitlines()]
        name = '"*"' if g.name == "*" else g.name
        lines += [f"  - resource: {g.resource}", f"    name: {name}",
                  f"    pattern: {g.pattern}", f"    operations: [{', '.join(g.ops)}]"]
    return "\n".join(lines) + "\n"


MERCHANT_GATEWAY = Account(
    "svc-merchant-gateway", "payments-edge",
    "merchant-gateway - turns merchant and acquirer authorisation requests into "
    f"{AUTH} events and registers that topic's producer schema.",
    (topic(AUTH, *W), Grant("cluster", "kafka-cluster", ("IDEMPOTENT_WRITE",))),
)
FRAUD_SCORING = Account(
    "svc-fraud-scoring", "cards-platform",
    "fraud-scoring - scores card authorisations and posts the result to the ledger.",
    (topic(AUTH, *R), group("fraud-scoring-consumer"), topic(LEDGER, *W)),
)
FRAUD_DECISIONING = Account(
    "svc-fraud-decisioning", "cards-platform",
    "fraud-decisioning-svc - approves or declines card authorisations and posts "
    "the result to the ledger. Replaced svc-fraud-scoring (ADR-0011).",
    (topic(AUTH, *R), group("fraud-decisioning-engine"), topic(LEDGER, *W)),
)
TXN_HISTORY = Account(
    "svc-txn-history-builder", "cards-servicing",
    "txn-history-builder - cardholder transaction history for the mobile and "
    "internet banking apps.",
    (topic(AUTH, *R), group("txn-history-builder")),
)
_STREAMS_INTERNAL = (
    "Kafka Streams internal topics (changelogs, repartition topics) are\n"
    "prefixed with the application.id."
)
_MAS_BASE = (
    topic(AUTH, *R),
    group("merchant-analytics-stream"),
    topic("merchant-analytics-stream-", "CREATE", "READ", "WRITE", "DESCRIBE",
          pattern="prefixed", comment=_STREAMS_INTERNAL),
)
_MAS_EOS = Grant("transactional_id", "merchant-analytics-stream", ("WRITE", "DESCRIBE"),
                 pattern="prefixed",
                 comment="processing.guarantee=exactly_once_v2: transactional ids start\n"
                         "with the application.id.")
MERCHANT_ANALYTICS_2022 = Account(
    "svc-merchant-analytics", "payments-edge",
    "merchant-analytics-stream - Kafka Streams application that aggregates card "
    "authorisations per merchant for the merchant portal.",
    _MAS_BASE,
)
MERCHANT_ANALYTICS_EOS = replace(MERCHANT_ANALYTICS_2022, grants=(*_MAS_BASE, _MAS_EOS))
MERCHANT_ANALYTICS = replace(MERCHANT_ANALYTICS_2022, grants=(
    *_MAS_BASE[:2],
    topic("merchant-analytics-stream-", "CREATE", "READ", "WRITE", "DESCRIBE", "DELETE",
          pattern="prefixed", comment=_STREAMS_INTERNAL),
    _MAS_EOS,
))
CLEARING = Account(
    "svc-clearing-settlement", "clearing-settlement",
    "clearing-settlement-svc - loads scheme clearing files, matches them to "
    "authorisations and builds the daily merchant settlement batches.",
    (topic("cards.clearing.received.v1", "READ", "WRITE", "DESCRIBE"),
     group("clearing-settlement-matcher"),
     topic("cards.clearing.matched.v1", *W),
     topic("cards.settlement.batch.posted.v1", *W)),
)
_CLEARING_FEES = (
    topic("cards.clearing.received.v1", "READ", "WRITE", "DESCRIBE"),
    group("clearing-settlement-matcher"),
    topic("cards.clearing.matched.v1", "READ", "WRITE", "DESCRIBE"),
    group("clearing-settlement-fees"),
    topic("cards.settlement.batch.posted.v1", *W),
    topic("cards.interchange.fee.calculated.v1", *W),
)
CLEARING_INTERCHANGE = replace(CLEARING, grants=_CLEARING_FEES)
CLEARING_JOURNAL = replace(CLEARING, grants=(*_CLEARING_FEES, topic("ledger.journal.posted.v1", *W)))
DISPUTES = Account(
    "svc-disputes", "cards-servicing",
    "disputes-svc - chargeback and refund case handling for the back office.",
    (topic("cards.chargeback.opened.v1", *W), topic("cards.chargeback.resolved.v1", *W),
     topic("cards.refund.requested.v1", *R), group("disputes-svc-refunds"),
     topic("cards.refund.completed.v1", *W)),
)
FRAUD_CASES = Account(
    "svc-fraud-case-management", "risk-platform",
    "fraud-case-management - opens and closes manual fraud investigation cases "
    "from the fraud score.",
    (topic("fraud.score.computed.v1", *R), group("fraud-case-management"),
     topic("fraud.case.opened.v1", *W), topic("fraud.case.resolved.v1", *W)),
)
AML = Account(
    "svc-aml-screening", "compliance-platform",
    "aml-transaction-monitoring - screens cleared card transactions and raises "
    "AML alerts for the compliance case-management system.",
    (topic("cards.clearing.matched.v1", *R), group("aml-transaction-monitoring"),
     topic("aml.transaction.screened.v1", *W), topic("aml.alert.raised.v1", *W)),
)
SANCTIONS = Account(
    "svc-sanctions-screening", "compliance-platform",
    "sanctions-screening - screens customers and cross-border payments against "
    "the OFAC, UN, EU and UK HMT lists.",
    (topic("sanctions.screening.completed.v1", *W),),
)
KYC = Account(
    "svc-kyc", "compliance-platform",
    "kyc-orchestrator - publishes KYC / CDD verification outcomes.",
    (topic("kyc.verification.completed.v1", *W),),
)
_CARD_TOPICS = tuple(topic(f"cards.card.{e}.v1", *W)
                     for e in ("issued", "activated", "blocked", "replaced"))
CARD_LIFECYCLE = Account(
    "svc-card-lifecycle", "cards-servicing",
    "card-lifecycle-svc - card issuance, activation, blocking and replacement.",
    _CARD_TOPICS,
)
CARD_LIFECYCLE_RISK = replace(CARD_LIFECYCLE, grants=(
    *_CARD_TOPICS, topic("risk.limit.breached.v1", *R), group("card-lifecycle-svc")))
STATEMENTS = Account(
    "svc-statements", "cards-servicing",
    "card-statements-batch - publishes an event when a cardholder's monthly "
    "statement is ready.",
    (topic("cards.statement.generated.v1", *W),),
)
CUSTOMER = Account(
    "svc-customer-profile", "customer-platform",
    "customer-profile-svc - customer onboarding, profile and consent records.",
    tuple(topic(f"customer.{t}.v1", *W) for t in ("account.opened", "profile.updated", "consent.granted")),
)
RISK_ENGINE = Account(
    "svc-risk-engine", "risk-platform",
    "risk-engine - velocity, exposure and spend-limit checks.",
    (topic("risk.limit.breached.v1", *W),),
)
DISPUTES_SEARCH = Account(
    "svc-disputes-search-connect", "cards-platform",
    "sink-elastic-disputes-search (Kafka Connect) - indexes chargeback events "
    "for the disputes back-office search.",
    (topic("cards.chargeback.opened.v1", *R), topic("cards.chargeback.resolved.v1", *R),
     group("connect-sink-elastic-disputes-search")),
)
CLEARING_ARCHIVE = Account(
    "svc-clearing-archive-connect", "cards-platform",
    "sink-gcs-clearing-archive (Kafka Connect) - archives matched clearing "
    "records to GCS for scheme reconciliation.",
    (topic("cards.clearing.matched.v1", *R), group("connect-sink-gcs-clearing-archive")),
)
GL_JOURNAL = Account(
    "svc-gl-journal", "cards-platform",
    "gl-journal-publisher - double-entry journal rows for the General Ledger "
    "from card postings, fees, refunds and chargebacks.",
    (topic("ledger.journal.posted.v1", *W),),
)
PARTNER_INGEST = Account(
    "svc-partner-settlement-ingest", "clearing-settlement",
    "partner-settlement-ingest - publishes the settlement files partner banks "
    "drop on SFTP, one record per posting, unchanged.",
    (topic(PARTNER_TOPIC, *W),),
    envs=(PROD_ENV,),
)
PARTNER_CONNECT = Account(
    "svc-partner-settlement-connect", "cards-platform",
    "sink-jdbc-partner-settlement (Kafka Connect) - loads partner settlement "
    "records into the settlement database and dead-letters the ones it cannot parse.",
    (topic(PARTNER_TOPIC, *R), group("connect-sink-jdbc-partner-settlement"),
     topic(PARTNER_DLQ, *W)),
    envs=(PROD_ENV,),
)
SRE = Account(
    "svc-sre-agent", "cards-platform",
    "SRE on-call tooling - read-only view of the cards clusters for incident "
    "investigation: topic metadata, configs and records, consumer-group members "
    "and offsets. No write, alter or delete. Records are tokenised (PCI DSS); "
    "payloads are never copied into tickets.",
    (topic("*", "READ", "DESCRIBE", "DESCRIBE_CONFIGS"),
     group("*", "DESCRIBE"),
     Grant("cluster", "kafka-cluster", ("DESCRIBE", "DESCRIBE_CONFIGS"))),
)


# ---------------------------------------------------------------------------
# CODEOWNERS
# ---------------------------------------------------------------------------

DOMAIN_OWNERS = {
    "cards": "cards-platform", "ledger": "cards-platform", "fraud": "risk-platform",
    "risk": "risk-platform", "aml": "compliance-platform", "sanctions": "compliance-platform",
    "kyc": "compliance-platform", "customer": "customer-platform",
}
PE = "@dss26-org/platform-engineering"


def render_codeowners(domains: list[str], accounts: list[Account]) -> str:
    lines = ["# Platform Engineering reviews every change. The squad that owns a",
             "# topic folder or a service account reviews it too.",
             f"*{' ' * 46}{PE}", ""]
    for d in domains:
        lines.append(f"{f'/topics/{d}/':<47}{PE} @dss26-org/{DOMAIN_OWNERS[d]}")
    lines.append("")
    for acc in sorted(accounts, key=lambda a: a.name):
        lines.append(f"{f'/acls/{acc.name}.yaml':<47}{PE} @dss26-org/{acc.owner}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The repo as a small world, rendered after every change
# ---------------------------------------------------------------------------


@dataclass
class World:
    era: str = "dc1"  # dc1 -> dc1+dev -> euw1
    schema: bool = False
    tags: bool = False
    console: str = "svc-control-center"
    topics: list[str] = field(default_factory=list)
    accounts: dict[str, Account] = field(default_factory=dict)
    static: dict[str, str] = field(default_factory=dict)

    def clusters(self) -> list[str]:
        return {"dc1": [PROD_ENV, DC1], "dc1+dev": [PROD_ENV, DEV_ENV, DC1],
                "euw1": [PROD_ENV, DEV_ENV]}[self.era]

    def placement(self, envs: tuple[str, ...]) -> list[str]:
        return [c for c in self.clusters() if c in envs or c == DC1]

    def render(self) -> dict[str, str]:
        files = dict(self.static)
        files["teams.yaml"] = _teams_yaml()
        for c in self.clusters():
            files[f"clusters/{c}.yaml"] = render_cluster(c, self.console)
        for name in self.topics:
            spec = SPECS[name]
            files[topic_path(name)] = render_topic(spec, self.placement(topic_envs(name)),
                                                   schema=self.schema, tags=self.tags)
        for acc in self.accounts.values():
            files[f"acls/{acc.name}.yaml"] = render_account(acc, self.placement(acc.envs))
        domains = sorted({n.split(".")[0] for n in self.topics},
                         key=lambda d: list(DOMAIN_OWNERS).index(d))
        files[".github/CODEOWNERS"] = render_codeowners(domains, list(self.accounts.values()))
        return files


class History:
    def __init__(self, world: World):
        self.world = world
        self.tree: dict[str, str] = {}
        self.commits: list[Commit] = []

    def commit(self, when: str, author: str, message: str) -> None:
        files = self.world.render()
        ops: list = [Write(p, files[p], executable=p.startswith("scripts/"))
                     for p in sorted(files) if self.tree.get(p) != files[p]]
        ops += [Delete(p) for p in sorted(set(self.tree) - set(files))]
        if not ops:
            raise ValueError(f"{REPO}: empty commit {message.splitlines()[0]!r}")
        self.commits.append(Commit(when, author, message, tuple(ops)))
        self.tree = files

    def add(self, *accounts: Account) -> None:
        for acc in accounts:
            self.world.accounts[acc.name] = acc


BOOTSTRAP_TOPICS = [
    AUTH, "cards.authorisation.responded.v1", "cards.authorisation.declined.v1",
    "cards.authorisation.reversed.v1", "cards.authorisation.captured.v1",
    "cards.clearing.received.v1", "cards.clearing.matched.v1",
    "cards.settlement.batch.posted.v1", LEDGER,
]


def _build_history() -> tuple[Commit, ...]:
    w = World()
    h = History(w)
    s = w.static
    s.update({
        "README.md": README.at(None),
        "catalog-info.yaml": CATALOG_INFO,
        ".github/pull_request_template.md": PR_TEMPLATE,
        ".gitignore": GITIGNORE,
        "requirements.txt": _requirements("6.0"),
        "scripts/validate.py": VALIDATE.at(None),
        ".github/workflows/validate.yml": WF_VALIDATE.at(None),
    })
    w.topics += BOOTSTRAP_TOPICS
    h.commit("2022-11-07 10:12", "tomasz.nowak",
             "chore: bootstrap kafka-platform from the kafka-dc1 topic inventory\n\n"
             "First step of the kafka-dc1 -> cards-prod-euw1 migration. The cards\n"
             "topics are declared as they run on kafka-dc1 today (same partitions and\n"
             "retention) and placed on both clusters while MirrorMaker 2 replicates.\n"
             "validate.py checks naming, owners and replication on every pull request\n"
             "so the new cluster starts clean.\n\nRefs: PLAT-412")

    h.add(MERCHANT_GATEWAY, FRAUD_SCORING, TXN_HISTORY, MERCHANT_ANALYTICS_2022, CLEARING)
    h.commit("2022-11-21 14:30", "tomasz.nowak",
             "feat(acls): service accounts for the cards producers and consumers\n\n"
             "The same grants these services have on kafka-dc1, now as code, so the\n"
             "cut-over does not depend on someone's shell history. SCRAM credentials\n"
             "for cards-prod-euw1 are issued into Vault per service; each squad moves\n"
             "its deployment over when it is ready.\n\nRefs: PLAT-418")

    w.era = "dc1+dev"
    s["README.md"] = README.at("dev")
    h.commit("2022-12-14 11:20", "erik.lindqvist",
             "feat(clusters): add cards-dev-euw1\n\n"
             "A development cluster in eu-west-1 so squads stop testing against the\n"
             "dev topics on kafka-dc1. Same topics and grants as production, except\n"
             "cards.ledger.posted.v1, which stays production-only (SOX scope).\n\n"
             "Refs: PLAT-431")

    w.era = "euw1"
    s["README.md"] = README.at("dc1-retired")
    h.commit("2023-02-06 09:40", "tomasz.nowak",
             "chore: decommission kafka-dc1\n\n"
             "merchant-analytics-stream was the last consumer to move (2023-01-30);\n"
             "every producer and consumer is now on cards-prod-euw1 and MirrorMaker 2\n"
             "is stopped. Drop kafka-dc1 from every\n"
             "topic and service account; the brokers are scheduled for shutdown.\n\n"
             "Refs: CHG-2207")

    w.schema = True
    s["README.md"] = README.at("schema")
    s["scripts/validate.py"] = VALIDATE.at("schema")
    h.commit("2023-02-13 15:10", "priya.r",
             "feat(schemas): declare Schema Registry subjects and BACKWARD compatibility\n\n"
             "ADR-0007 puts every card event in Avro with one subject per topic, and the\n"
             "schema evolution policy says cards subjects are BACKWARD so a producer\n"
             "upgrade never breaks a consumer still on the previous schema. Until now\n"
             "the level was whatever each registry defaulted to. Declaring it here\n"
             "makes it reviewable, and validate.py now rejects anything weaker than\n"
             "BACKWARD on a cards subject.\n\nRefs: CARDS-842")

    s["tests/test_validate.py"] = TESTS.at(None)
    s["README.md"] = README.at("tests")
    s[".github/workflows/validate.yml"] = WF_VALIDATE.at("tests")
    h.commit("2023-03-09 10:30", "erik.lindqvist",
             "test: unit tests for validate.py, run in CI\n\n"
             "One test per rule against a throwaway tree, plus one that validates the\n"
             "repository itself, so a rule change cannot silently start passing bad\n"
             "definitions.")

    w.topics += ["cards.chargeback.opened.v1", "cards.chargeback.resolved.v1",
                 "cards.refund.requested.v1", "cards.refund.completed.v1"]
    h.add(DISPUTES)
    h.commit("2023-04-18 14:05", "chloe.dubois",
             "feat(cards): chargeback and refund topics for disputes-svc\n\n"
             "disputes-svc moves off the nightly chargeback file. Owner stays\n"
             "cards-platform like every cards.* topic; cards-servicing is the producer.\n\n"
             "Refs: CARDS-871")

    s["docs/service-accounts.md"] = SA_DOC.at(None)
    s["README.md"] = README.at("service-accounts-doc")
    h.commit("2023-05-09 11:15", "dana.v",
             "docs: service account and ACL conventions\n\n"
             "Access requests keep asking the same questions: what to call the\n"
             "principal, which grants a consumer needs, where the credentials come\n"
             "from. Write the answers down in docs/service-accounts.md, next to the\n"
             "files they apply to, and link it from the README.\n\nRefs: CARDS-884")

    w.topics.append("cards.interchange.fee.calculated.v1")
    h.add(CLEARING_INTERCHANGE)
    h.commit("2023-06-20 10:05", "henrik.larsen",
             "feat(cards): add cards.interchange.fee.calculated.v1\n\n"
             "Per-transaction interchange and scheme fees, computed by\n"
             "clearing-settlement-svc from matched clearing records (new group\n"
             "clearing-settlement-fees) for revenue analytics and the GL fee accruals.\n\n"
             "Refs: CARDS-902")

    w.topics += ["fraud.score.computed.v1", "fraud.case.opened.v1", "fraud.case.resolved.v1"]
    h.add(FRAUD_CASES)
    h.commit("2023-07-11 13:20", "ines.duarte",
             "feat(fraud): fraud score and fraud case topics\n\n"
             "First risk-platform topics on the cards clusters: the per-authorisation\n"
             "fraud score and the manual investigation case lifecycle.\n\nRefs: RISK-140")

    s["requirements.txt"] = _requirements("6.0.1")
    h.commit("2023-07-25 09:02", "platform-bot",
             "chore(deps): bump pyyaml from 6.0 to 6.0.1\n\n"
             "6.0.1 fixes building PyYAML from source with Cython 3.")

    s["scripts/apply.py"] = _src("scripts/apply.py")
    s["tests/test_apply.py"] = _src("tests/test_apply.py")
    s[".github/workflows/apply.yml"] = wf_apply("v3")
    s[".github/actionlint.yaml"] = _src(".github/actionlint.yaml")
    s["requirements.txt"] = _requirements("6.0.1", "2.2.0")
    s["README.md"] = README.at("apply")
    h.commit("2023-08-22 16:30", "fatima.benali",
             "feat: apply merged changes with scripts/apply.py\n\n"
             "Until now the platform on-call applied every merged change by hand with\n"
             "kafka-topics and kafka-acls, which is how cards-dev-euw1 drifted from git.\n"
             "apply.py plans against the live cluster and only creates or raises -\n"
             "nothing is ever deleted - and sets each subject's compatibility level.\n"
             "It runs on the cards-kafka-admin runners: dev first, prod behind an\n"
             "environment approval.\n\nRefs: PLAT-506")

    s[".github/workflows/validate.yml"] = WF_VALIDATE.at("checkout-v4")
    s[".github/workflows/apply.yml"] = wf_apply("v4")
    h.commit("2023-09-12 09:15", "platform-bot",
             "chore(deps): bump actions/checkout from 3 to 4\n\n"
             "v4 runs on Node 20; Node 16 actions are deprecated on GitHub runners.")

    w.topics += ["aml.transaction.screened.v1", "aml.alert.raised.v1",
                 "sanctions.screening.completed.v1", "kyc.verification.completed.v1"]
    h.add(AML, SANCTIONS, KYC)
    h.commit("2023-10-17 14:40", "kwame.mensah",
             "feat(compliance): AML, sanctions and KYC topics\n\n"
             "Screening results move from the nightly batch export to events, so case\n"
             "management sees an alert minutes after the transaction clears.\n\n"
             "Refs: CMP-212")

    h.add(MERCHANT_ANALYTICS_EOS)
    s["docs/service-accounts.md"] = SA_DOC.at("transactional")
    h.commit("2023-11-16 11:35", "marta.silva",
             "feat(acls): transactional ids for merchant-analytics-stream\n\n"
             "Moving the KPI stores to processing.guarantee=exactly_once_v2: a\n"
             "rebalance replayed a window and double-counted a merchant's volume. The\n"
             "Streams producers need WRITE and DESCRIBE on transactional ids prefixed\n"
             "with the application.id.\n\nRefs: PAY-288")

    w.topics += ["cards.card.issued.v1", "cards.card.activated.v1", "cards.card.blocked.v1",
                 "cards.card.replaced.v1", "cards.statement.generated.v1"]
    h.add(CARD_LIFECYCLE, STATEMENTS)
    h.commit("2023-11-28 11:10", "mateo.rossi",
             "feat(cards): card lifecycle and statement topics\n\n"
             "card-lifecycle-svc and statements-builder publish events instead of\n"
             "writing to the shared servicing database.\n\nRefs: CARDS-951")

    w.topics += ["customer.account.opened.v1", "customer.profile.updated.v1",
                 "customer.consent.granted.v1"]
    h.add(CUSTOMER)
    h.commit("2024-01-16 10:25", "aiko.tanaka",
             "feat(customer): customer account, profile and consent topics\n\n"
             "Personal data, so 7-day retention (GDPR data minimisation): consumers\n"
             "keep their own projections, the topic is not a store.\n\nRefs: CUST-318")

    s[".github/workflows/validate.yml"] = WF_VALIDATE.at("setup-python-v5")
    h.commit("2024-01-30 09:10", "platform-bot",
             "chore(deps): bump actions/setup-python from 4 to 5")

    w.topics.append("cards.authorisation.expired.v1")
    h.commit("2024-03-05 15:55", "priya.r",
             "feat(cards): add cards.authorisation.expired.v1\n\n"
             "Auth holds that age out before capture. The ledger releases the held\n"
             "funds from it; merchant analytics tracks unrealised auths.\n\n"
             "Refs: CARDS-998")

    h.add(MERCHANT_ANALYTICS)
    h.commit("2024-03-19 11:30", "ravi.iyer",
             "fix(acls): DELETE on merchant-analytics-stream internal topics\n\n"
             "Kafka Streams purges consumed repartition records with deleteRecords.\n"
             "Without DELETE the purge fails quietly and the by-merchant repartition\n"
             "topic only shrinks at retention.\n\nRefs: PAY-341")

    w.topics.append("risk.limit.breached.v1")
    h.add(RISK_ENGINE, CARD_LIFECYCLE_RISK)
    h.commit("2024-04-09 14:15", "yusuf.demir",
             "feat(risk): add risk.limit.breached.v1\n\n"
             "Velocity and exposure breaches from the risk engine. card-lifecycle-svc\n"
             "reads it to block a card automatically on the breach types agreed with\n"
             "Cards Servicing (group card-lifecycle-svc).\n\nRefs: RISK-187")

    h.add(DISPUTES_SEARCH)
    s["docs/service-accounts.md"] = SA_DOC.at("connect")
    h.commit("2024-05-14 10:40", "sam.okafor",
             "feat(acls): svc-disputes-search-connect for sink-elastic-disputes-search\n\n"
             "First connector with its own principal rather than the Connect worker's,\n"
             "so its grants cover its own topics and group only. The workers now run\n"
             "with connector.client.config.override.policy=Principal; convention\n"
             "added to docs/service-accounts.md.\n\nRefs: CARDS-1032")

    h.add(FRAUD_DECISIONING)
    h.commit("2024-05-28 10:00", "alex.chen",
             "feat(acls): add svc-fraud-decisioning next to svc-fraud-scoring (ADR-0011)\n\n"
             "fraud-scoring becomes fraud-decisioning-svc now that it makes the\n"
             "approve/decline decision, and its consumer group becomes\n"
             "fraud-decisioning-engine. Both principals exist during the cut-over so\n"
             "we can roll back; svc-fraud-scoring goes once fraud-scoring-consumer is\n"
             "drained.\n\nRefs: CARDS-1041")

    del w.accounts[FRAUD_SCORING.name]
    h.commit("2024-06-18 16:20", "alex.chen",
             "chore(acls): remove svc-fraud-scoring after the fraud-decisioning cut-over\n\n"
             "fraud-decisioning-engine has consumed cards.authorisation.requested.v1\n"
             "since 2024-06-11 and fraud-scoring-consumer was deleted yesterday.\n"
             "ADR-0011 is complete.\n\nRefs: CARDS-1041")

    s["requirements.txt"] = _requirements("6.0.2", "2.2.0")
    h.commit("2024-08-13 09:05", "platform-bot", "chore(deps): bump pyyaml from 6.0.1 to 6.0.2")

    h.add(CLEARING_ARCHIVE)
    h.commit("2024-08-20 14:35", "sam.okafor",
             "feat(acls): svc-clearing-archive-connect for sink-gcs-clearing-archive\n\n"
             "Refs: CARDS-1104")

    w.topics.append("ledger.journal.posted.v1")
    h.add(GL_JOURNAL, CLEARING_JOURNAL)
    h.commit("2024-09-10 11:00", "priya.r",
             "feat(ledger): add ledger.journal.posted.v1\n\n"
             "Generic double-entry journal for the General Ledger. Card postings,\n"
             "fees, refunds and chargebacks publish through svc-gl-journal;\n"
             "clearing-settlement-svc publishes its scheme payables directly. It is the\n"
             "replay source for SOX reconciliations, hence 30 days.\n\nRefs: CARDS-1117")

    s[".github/workflows/validate.yml"] = WF_VALIDATE.at("py312")
    h.commit("2024-11-05 10:20", "fatima.benali", "ci: run validate on Python 3.12")

    w.tags = True
    s["README.md"] = README.at("tags")
    s["scripts/validate.py"] = VALIDATE.at("tags")
    s["tests/test_validate.py"] = TESTS.at("tags")
    h.commit("2025-01-21 14:10", "priya.r",
             "feat(topics): catalogue tags on every topic\n\n"
             "Lenses replaced Control Center as the Kafka console this month, and its\n"
             "topic catalogue shows each topic's description and tags. Same tag set as\n"
             "the Confluence topic catalogue: domain, owner, criticality, compliance\n"
             "scope, PII level, residency and event type. validate.py checks that the\n"
             "tags agree with the owner, tier and folder of the file.\n\nRefs: CARDS-1189")

    w.console = "svc-lenses"
    h.commit("2025-01-28 09:45", "erik.lindqvist",
             "chore(clusters): svc-lenses replaces svc-control-center in super.users\n\n"
             "Confluent Control Center is retired on both clusters.\n\nRefs: PLAT-688")

    s["README.md"] = README.at("contacts")
    h.commit("2025-02-17 10:30", "erik.lindqvist",
             "docs(readme): update out-of-hours contacts and dashboards\n\n"
             "Paging moved from Opsgenie to PagerDuty and the Kafka dashboards live in\n"
             "Datadog EU now.")

    s["requirements.txt"] = _requirements("6.0.2", "2.10.0")
    h.commit("2025-05-13 09:00", "platform-bot", "chore(deps): bump confluent-kafka from 2.2.0 to 2.10.0")

    s[".github/workflows/validate.yml"] = WF_VALIDATE.at("checkout-v5")
    s[".github/workflows/apply.yml"] = wf_apply("v5")
    h.commit("2025-09-02 08:10", "platform-bot", "chore(deps): bump actions/checkout from 4 to 5")

    w.topics += [PARTNER_TOPIC, PARTNER_DLQ]
    h.add(PARTNER_INGEST, PARTNER_CONNECT)
    s["README.md"] = README.at("dlq")
    s["scripts/validate.py"] = VALIDATE.at("dlq")
    s["tests/test_validate.py"] = TESTS.at("dlq")
    h.commit("2025-10-20 15:20", "sam.okafor",
             "feat(cards): partner settlement topic and its dead-letter queue\n\n"
             "Partner banks send settlement as hand-built JSON, published unchanged by\n"
             "svc-partner-settlement-ingest. sink-jdbc-partner-settlement\n"
             "tolerates bad records and routes them to cards.partner.settlement.v1.dlq\n"
             "with context headers, so the DLQ runbook can read the failure reason.\n"
             "Production only for now. validate.py checks that a .dlq topic names the\n"
             "topic it serves and stores raw bytes.\n\nRefs: CARDS-1338")

    s[".github/workflows/validate.yml"] = WF_VALIDATE.at("setup-python-v6")
    h.commit("2025-10-28 09:00", "platform-bot", "chore(deps): bump actions/setup-python from 5 to 6")

    h.add(SRE)
    s["README.md"] = README.at("wildcard")
    s["docs/service-accounts.md"] = SA_DOC.at("read-only")
    s["scripts/validate.py"] = VALIDATE.at("wildcard")
    s["tests/test_validate.py"] = TESTS.at("wildcard")
    h.commit("2025-12-09 11:40", "dana.v",
             "feat(acls): read-only svc-sre-agent for the SRE on-call tooling\n\n"
             "Read access across the cards clusters for incident investigation, as\n"
             "agreed in the access standard (Access to Kafka and Lenses): topic\n"
             "metadata, configs and records, consumer-group members and offsets. No\n"
             "write, alter or delete anywhere, and no group READ - it never joins a\n"
             "group. validate.py now rejects a wildcard grant that is not read-only.\n\n"
             "Refs: CARDS-1371")

    s["docs/service-accounts.md"] = SA_DOC.at("rotation")
    h.commit("2026-02-24 10:05", "erik.lindqvist",
             "docs(service-accounts): credentials now rotate every 60 days\n\n"
             "Vault's rotation policy for SCRAM credentials changed with the updated\n"
             "secrets standard. Services already reload them without a restart.\n\n"
             "Refs: PLAT-1127")

    s["requirements.txt"] = _requirements("6.0.3", "2.10.0")
    h.commit("2026-06-16 09:00", "platform-bot", "chore(deps): bump pyyaml from 6.0.2 to 6.0.3")

    assert s["README.md"] == README.final
    assert s["scripts/validate.py"] == VALIDATE.final
    assert s["tests/test_validate.py"] == TESTS.final
    assert s["docs/service-accounts.md"] == SA_DOC.final
    assert s[".github/workflows/validate.yml"] == WF_VALIDATE.final
    assert s[".github/workflows/apply.yml"] == _WF_APPLY
    assert sorted(w.topics) == sorted(SPECS), "every catalogue topic must be declared"
    return tuple(h.commits)


HISTORY = _build_history()

# The topic files must agree with the catalogue the clusters were built from.
for _t in TOPICS:
    assert f"partitions: {_t.partitions}\n" in render_topic(_t, list(topic_envs(_t.name)), schema=True, tags=True)


ANALYTICS_ACL = "acls/svc-merchant-analytics.yaml"

PRS: tuple[ScenarioPR, ...] = (
    ScenarioPR(
        key="kafka-platform-merchant-analytics-v2-acl",
        kind="decoy",
        scenario="consumer-lag",
        branch="fatima/merchant-analytics-v2-group-acl",
        title=f"feat(acl): prefixed group grant for merchant-analytics-stream v2 on {AUTH}",
        body=(
            "## What\n"
            "`svc-merchant-analytics`: switch the consumer-group grant from the literal "
            "`merchant-analytics-stream` to a prefixed match.\n\n"
            "## Why\n"
            "payments-edge is rolling out merchant-analytics-stream v2 as a second Kafka "
            "Streams application (`application.id=merchant-analytics-stream-v2`) running "
            "next to v1, so they can compare the merchant KPIs before cutting the portal over "
            "(PAY-618). Its internal topics already match the existing "
            "`merchant-analytics-stream-` prefix; only the group grant was literal, so v2 "
            "fails to join its group on startup.\n\n"
            "## Impact\n"
            f"Only `svc-merchant-analytics` changes, on cards-prod-euw1 and cards-dev-euw1. "
            f"Its grant on `{AUTH}` stays READ/DESCRIBE, and the internal-topic and "
            "transactional-id grants already use the `merchant-analytics-stream` prefix. "
            "No other service account is touched. The old literal group "
            "grant becomes redundant; `apply` will list it as unmanaged until PLAT removes it.\n\n"
            "## Checklist\n"
            "- [x] `python3 scripts/validate.py` passes locally\n"
            "- [x] The owning squad has reviewed (ravi.iyer, payments-edge)\n"
            "- [ ] New write access to a tier-1 topic in production: n/a, consumer group only"
        ),
        author="fatima.benali",
        commit_message=(
            "feat(acl): prefixed group grant for merchant-analytics-stream v2\n\n"
            "merchant-analytics-stream v2 runs next to v1 under application.id\n"
            "merchant-analytics-stream-v2 until the cut-over.\n\nRefs: PAY-618"
        ),
        ops=(Edit(
            ANALYTICS_ACL,
            "  - resource: group\n    name: merchant-analytics-stream\n    pattern: literal\n",
            "  # Prefixed so v1 and v2 (application.id merchant-analytics-stream-v2)\n"
            "  # can consume side by side during the v2 rollout.\n"
            "  - resource: group\n    name: merchant-analytics-stream\n    pattern: prefixed\n",
        ),),
        labels=("acl", "access-request"),
    ),
)


REPO_SPEC = RepoSpec(
    name=REPO,
    description="Topics, Schema Registry subjects, service accounts and ACLs for the cards Kafka clusters, as code.",
    team="platform-engineering",
    domain="platform",
    tier="A",
    topics=("kafka", "gitops", "schema-registry", "acl", "team-platform-engineering",
            "domain-platform"),
    history=HISTORY,
    prs=PRS,
    labels=DEFAULT_LABELS + (
        Label("acl", "5319e7", "Service accounts and ACLs"),
        Label("topics", "1d76db", "Topic definitions"),
        Label("access-request", "c5def5", "Access requested by another squad"),
    ),
    # CODEOWNERS names every squad that owns a topic folder or a service
    # account, and GitHub only honours code owners with write access.
    team_access=tuple((t, "push") for t in (
        "cards-platform", "payments-edge", "cards-servicing", "clearing-settlement",
        "risk-platform", "compliance-platform", "customer-platform",
    )),
)
