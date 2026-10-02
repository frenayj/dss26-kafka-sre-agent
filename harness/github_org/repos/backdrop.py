"""dss26-org neighbour (Tier B) and backdrop (Tier C) repositories.

Tier B - neighbours that turn up when someone code-searches the org for the
incident's topics and consumer groups: txn-history-builder and
merchant-analytics-stream read cards.authorisation.requested.v1 alongside
fraud-decisioning-engine; disputes-svc owns the index behind
sink-elastic-disputes-search; clearing-settlement-svc calls the shared
schema-compat workflow; card-lifecycle-svc and fraud-case-management sit one
hop away. Tier C - the rest of a retail bank (financial crime, customer,
channels, core banking, statements), so the cards estate does not look like a
lab.

Story role: exactly one ScenarioPR, a decoy in txn-history-builder (a fetch
tuning change on its cards.authorisation.requested.v1 consumer, merged the
morning of the consumer-lag incident). It is harmless: a different consumer
group from fraud-decisioning-engine, and only batching changes.

How histories are declared: ``F(path)`` writes ``files/<repo>/<path>`` as it
looked at that commit, and ``S(path, old, new)`` is a later Edit. ``F`` is
derived from the final file by undoing every later ``S`` on the same path, so
the files under ``files/`` are always the head of ``main`` and each history
step is a small, reviewable diff.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Union

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

sys.path.insert(0, str(REPO_ROOT / "harness" / "seed"))
from demo_topics import TOPICS  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class F:
    """Write files/<repo>/<path> as it stood at this commit."""

    path: str
    executable: bool = False


@dataclass(frozen=True)
class S:
    """A swap: an Edit at this commit, undone to derive earlier versions."""

    path: str
    old: str
    new: str


Op = Union[F, S, Write, Edit, Delete]


def history(repo: str, *commits: tuple[str, str, str, tuple[Op, ...]]) -> tuple[Commit, ...]:
    """Turn (when, author, message, ops) tuples into Commits, resolving F and S."""
    out: list[Commit] = []
    for i, (when, author, message, ops) in enumerate(commits):
        real: list = []
        for op in ops:
            if isinstance(op, F):
                text = (FILES_ROOT / repo / op.path).read_text()
                later = [s for c in commits[i + 1:] for s in c[3] if isinstance(s, S) and s.path == op.path]
                for s in reversed(later):
                    if text.count(s.new) != 1:
                        raise ValueError(f"{repo}/{op.path}: cannot undo swap {s.new[:60]!r} "
                                         f"(found {text.count(s.new)} times)")
                    text = text.replace(s.new, s.old, 1)
                real.append(Write(op.path, text, executable=op.executable))
            elif isinstance(op, S):
                real.append(Edit(op.path, op.old, op.new))
            else:
                real.append(op)
        out.append(Commit(when, author, message, tuple(real)))
    return tuple(out)


def final(repo: str, path: str, start: str, end: str) -> str:
    """The slice of the final file from ``start`` up to and including ``end``."""
    text = (FILES_ROOT / repo / path).read_text()
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[i:j]


def rewind(repo: str, path: str, *swaps: S) -> str:
    """The final file with ``swaps`` (given in chronological order) undone."""
    text = (FILES_ROOT / repo / path).read_text()
    for s in reversed(swaps):
        if text.count(s.new) != 1:
            raise ValueError(f"{repo}/{path}: cannot rewind {s.new[:60]!r}")
        text = text.replace(s.new, s.old, 1)
    return text


_TOPICS = {t.name: t for t in TOPICS}

# The producer's v1 schema, as consumers of cards.authorisation.requested.v1 vendor it.
AUTH_V1_AVSC = (REPO_ROOT / "harness/stack/schemas/cards_authorisation_requested_v1.avsc").read_text()
AUTH_TOPIC = "cards.authorisation.requested.v1"


def avsc(topic: str) -> str:
    schema = _TOPICS[topic].avro_schema
    if schema is None:
        raise ValueError(f"{topic} has no catalogue schema")
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def avro(directory: str, *topics: str) -> tuple[Write, ...]:
    return tuple(Write(f"{directory}/{t}.avsc", avsc(t)) for t in topics)


def _yaml_scalar(value: str) -> str:
    """Plain YAML scalar when safe, double-quoted otherwise."""
    if ": " in value or " #" in value or value[:1] in "!&*?|>'\"%@`{[-,":
        return json.dumps(value, ensure_ascii=False)
    return value


def catalog_info(name: str, *, title: str, description: str, owner: str, system: str,
                 tags: tuple[str, ...], type: str = "service", lifecycle: str = "production",
                 pagerduty: str | None = None, opsgenie: str | None = None, dashboard: str | None = None,
                 consumes: tuple[str, ...] = (), produces: tuple[str, ...] = (),
                 groups: tuple[str, ...] = (), depends_on: tuple[str, ...] = (),
                 links: tuple[tuple[str, str], ...] = ()) -> str:
    ann = [f"github.com/project-slug: dss26-org/{name}", "backstage.io/techdocs-ref: dir:."]
    if pagerduty:
        ann.append(f"pagerduty.com/service-id: {pagerduty}")
    if opsgenie:
        ann.append(f'opsgenie.com/team: "{opsgenie}"')
    if dashboard:
        ann.append(f'datadoghq.com/dashboard-url: "{dashboard}"')
    if consumes:
        ann.append(f"dss26.bank/kafka-consumes: {','.join(consumes)}")
    if produces:
        ann.append(f"dss26.bank/kafka-produces: {','.join(produces)}")
    if groups:
        ann.append(f"dss26.bank/consumer-group: {','.join(groups)}")
    lines = [
        "apiVersion: backstage.io/v1alpha1",
        "kind: Component",
        "metadata:",
        f"  name: {name}",
        f"  title: {_yaml_scalar(title)}",
        f"  description: {_yaml_scalar(description)}",
        "  annotations:",
        *(f"    {a}" for a in ann),
        f"  tags: [{', '.join(tags)}]",
    ]
    if links:
        lines.append("  links:")
        for url, link_title in links:
            lines += [f"    - url: {url}", f"      title: {_yaml_scalar(link_title)}"]
    lines += [
        "spec:",
        f"  type: {type}",
        f"  lifecycle: {lifecycle}",
        f"  owner: group:{owner}",
        f"  system: {system}",
    ]
    if depends_on:
        lines.append("  dependsOn:")
        lines += [f"    - {d}" for d in depends_on]
    return "\n".join(lines) + "\n"


def dd(slug: str, name: str) -> str:
    return f"https://app.datadoghq.eu/dashboard/{slug}/{name}"


ADR_0007 = ("https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980034049/ADR-0007+Avro+and+Schema+Registry+for+card+events",
            "ADR-0007 - Avro and Schema Registry for card events")

L_KAFKA = Label("kafka", "5319e7", "Kafka clients, topics and schemas")
L_PERF = Label("performance", "fbca04")
L_SCHEMA = Label("schema", "c5def5", "Avro schema change - check consumers")
L_COMPLIANCE = Label("compliance", "0e8a16", "Needs a compliance partner review")
L_A11Y = Label("accessibility", "1d76db", "European Accessibility Act / WCAG 2.1 AA")

GITIGNORE_GRADLE = "build/\n.gradle/\n.kotlin/\n*.iml\n.idea/\nout/\n"
GITIGNORE_MAVEN = "target/\n*.iml\n.idea/\n.vscode/\n"

# ===========================================================================
# Tier B - txn-history-builder (cards-servicing, Kotlin)
# ===========================================================================

TXN = "txn-history-builder"
TXN_PKG = "src/main/kotlin/com/dss26/cards/txnhistory"
TXN_LISTENER = f"{TXN_PKG}/kafka/AuthorisationListener.kt"
TXN_REPO = f"{TXN_PKG}/history/CardTransactionRepository.kt"
TXN_MODEL = f"{TXN_PKG}/history/CardTransaction.kt"
TXN_APP = f"{TXN_PKG}/TxnHistoryApplication.kt"
TXN_API = f"{TXN_PKG}/api/TransactionHistoryController.kt"
TXN_YML = "src/main/resources/application.yml"
TXN_GRADLE = "build.gradle.kts"
TXN_TEST = "src/test/kotlin/com/dss26/cards/txnhistory/history/CardTransactionMapperTest.kt"

TXN_CATALOG = catalog_info(
    TXN,
    title="Cardholder transaction history",
    description="Builds the card transaction history the apps show, from cards.authorisation.requested.v1.",
    owner="cards-servicing", system="card-servicing",
    tags=("kotlin", "spring-boot", "kafka", "postgres", "tier-2"),
    dashboard=dd("k3x-9qd-2mf", TXN),
    consumes=(AUTH_TOPIC,), groups=(TXN,),
    depends_on=("resource:txn-history-db",),
    links=(ADR_0007,),
)

TXN_CODEOWNERS = """\
*                         @dss26-org/cards-servicing
# Vendored copy of the producer's schema: Payments Edge reviews changes to it.
/src/main/avro/           @dss26-org/cards-servicing @dss26-org/payments-edge
"""

TXN_README_2022 = """\
# txn-history-builder

Builds the cardholder transaction history shown in the mobile and internet
banking apps. Consumes `cards.authorisation.requested.v1` (consumer group
`txn-history-builder`), keeps one row per `auth_id` in Postgres and serves it
on `GET /v1/cards/{cardToken}/transactions`.

## Running locally

```bash
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092 SCHEMA_REGISTRY_URL=http://localhost:8081
export KAFKA_SECURITY_PROTOCOL=PLAINTEXT
export TXN_HISTORY_DB_URL=jdbc:postgresql://localhost:5432/txn_history
export TXN_HISTORY_DB_USER=txn_history TXN_HISTORY_DB_PASSWORD=txn_history
gradle bootRun
```

## Owners

Cards Servicing, `#cards-servicing`.
"""

TXN_API_2022 = """\
package com.dss26.cards.txnhistory.api

import com.dss26.cards.txnhistory.history.CardTransaction
import com.dss26.cards.txnhistory.history.CardTransactionRepository
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/v1/cards/{cardToken}/transactions")
class TransactionHistoryController(private val repository: CardTransactionRepository) {

    @GetMapping
    fun list(
        @PathVariable cardToken: String,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "50") size: Int,
    ): List<CardTransaction> = repository.findByCard(cardToken, page, size.coerceIn(1, 200))
}
"""

_TXN_PLUGINS = """\
    id("org.springframework.boot") version "{boot}"
    id("io.spring.dependency-management") version "{depmgmt}"
    id("com.github.davidmc24.gradle.plugin.avro") version "{avro}"
    kotlin("jvm") version "{kotlin}"
    kotlin("plugin.spring") version "{kotlin}"
"""
TXN_PLUGINS_2022 = _TXN_PLUGINS.format(boot="2.6.7", depmgmt="1.0.11.RELEASE", avro="1.3.0", kotlin="1.6.21")
TXN_PLUGINS_2023 = _TXN_PLUGINS.format(boot="3.1.2", depmgmt="1.1.3", avro="1.8.0", kotlin="1.9.0")
TXN_PLUGINS_2024 = _TXN_PLUGINS.format(boot="3.3.5", depmgmt="1.1.6", avro="1.9.1", kotlin="2.0.21")

TXN_RECORD_LISTENER_2022 = r"""    @KafkaListener(id = "authorisations", topics = ["\${txn-history.topic}"])
    fun onAuthorisation(record: ConsumerRecord<String, CardAuthEvent>) {
        val auth = record.value()
        repository.upsert(auth.toCardTransaction(record.partition(), record.offset()))
        written.increment()
        log.debug("Wrote {}", auth.authId)
    }
"""
TXN_RECORD_LISTENER_TIER = r"""    @KafkaListener(id = "authorisations", topics = ["\${txn-history.topic}"])
    fun onAuthorisation(record: ConsumerRecord<String, CardAuthEvent>) {
        val auth = record.value()
        if (auth.tier !in properties.acceptedTiers) {
            ignoredTier.increment()
            return
        }
        repository.upsert(auth.toCardTransaction(record.partition(), record.offset()))
        written.increment()
        log.debug("Wrote {}", auth.authId)
    }
"""

TXN_HISTORY = history(
    TXN,
    ("2022-05-09 10:14", "chloe.dubois",
     "feat: build the cardholder transaction history from card authorisations\n\n"
     "The apps currently show yesterday's statement lines only. This service\n"
     "consumes cards.authorisation.requested.v1 (Avro, ADR-0007) as group\n"
     "txn-history-builder and keeps one row per auth_id in Postgres, so a\n"
     "purchase shows up in the app seconds after the card is used. The BFFs\n"
     "read it through GET /v1/cards/{cardToken}/transactions.\n\n"
     "Refs: CSERV-231",
     (
         Write("README.md", TXN_README_2022),
         Write("catalog-info.yaml", TXN_CATALOG),
         Write(".github/CODEOWNERS", TXN_CODEOWNERS),
         F(".github/workflows/ci.yml"),
         Write(".gitignore", GITIGNORE_GRADLE),
         F("settings.gradle.kts"),
         F(TXN_GRADLE),
         Write(f"src/main/avro/{AUTH_TOPIC}.avsc", AUTH_V1_AVSC),
         F(TXN_APP),
         F(TXN_LISTENER),
         F(TXN_MODEL),
         F(TXN_REPO),
         Write(TXN_API, TXN_API_2022),
         F(TXN_YML),
         F("src/main/resources/db/migration/V1__card_transaction.sql"),
         F(TXN_TEST),
         F("deploy/values-prod.yaml"),
     )),
    ("2022-11-28 14:05", "chloe.dubois",
     "fix: keep non-prod authorisations out of cardholder history\n\n"
     "Scheme certification runs through the live gateway with test cards, and\n"
     "the gateway stamps those records tier=dev. They were landing in the\n"
     "history table next to real purchases. Filter on tier, configurable so a\n"
     "uat deployment can accept both.\n\n"
     "Refs: CSERV-268",
     (
         F(f"{TXN_PKG}/history/TxnHistoryProperties.kt"),
         S(TXN_APP,
           "import org.springframework.boot.autoconfigure.SpringBootApplication\n"
           "import org.springframework.boot.runApplication",
           "import org.springframework.boot.autoconfigure.SpringBootApplication\n"
           "import org.springframework.boot.context.properties.ConfigurationPropertiesScan\n"
           "import org.springframework.boot.runApplication"),
         S(TXN_APP, "@SpringBootApplication\nclass", "@SpringBootApplication\n@ConfigurationPropertiesScan\nclass"),
         S(TXN_LISTENER,
           "import com.dss26.cards.txnhistory.history.CardTransactionRepository\n"
           "import com.dss26.cards.txnhistory.history.toCardTransaction",
           "import com.dss26.cards.txnhistory.history.CardTransactionRepository\n"
           "import com.dss26.cards.txnhistory.history.TxnHistoryProperties\n"
           "import com.dss26.cards.txnhistory.history.toCardTransaction"),
         S(TXN_LISTENER,
           "    private val repository: CardTransactionRepository,\n    meterRegistry: MeterRegistry,",
           "    private val repository: CardTransactionRepository,\n"
           "    private val properties: TxnHistoryProperties,\n    meterRegistry: MeterRegistry,"),
         S(TXN_LISTENER,
           '    private val written = meterRegistry.counter("txn_history.transactions.written")\n',
           '    private val written = meterRegistry.counter("txn_history.transactions.written")\n'
           '    private val ignoredTier = meterRegistry.counter("txn_history.transactions.ignored", "reason", "tier")\n'),
         S(TXN_LISTENER, TXN_RECORD_LISTENER_2022, TXN_RECORD_LISTENER_TIER),
         S(TXN_YML, "  topic: cards.authorisation.requested.v1\n",
           "  topic: cards.authorisation.requested.v1\n  accepted-tiers: prod\n"),
     )),
    ("2023-01-24 10:30", "chloe.dubois",
     "chore(deploy): consume from cards-prod-euw1\n\n"
     "Our part of the kafka-dc1 exit. MirrorMaker 2 translated the group's\n"
     "committed offsets, so txn-history-builder resumes on cards-prod-euw1\n"
     "where it stopped on dc1. Any overlap is absorbed by the auth_id upsert.\n\n"
     "Refs: PLAT-212",
     (S("deploy/values-prod.yaml", "      name: kafka-dc1\n", "      name: kafka-cards-prod-euw1\n"),)),
    ("2023-06-12 11:20", "mateo.rossi",
     "fix: skip records we cannot deserialise instead of stopping the partition\n\n"
     "On Friday a load test pointed at the wrong cluster wrote records with a\n"
     "schema id that only exists in the dev registry. The container could not\n"
     "get past the first one and partition 4 stood still for 40 minutes.\n\n"
     "The transaction still reaches the statement through clearing, so a gap\n"
     "here is cosmetic. Wrap the Avro deserializer in ErrorHandlingDeserializer,\n"
     "retry twice, then log, count (txn_history.records.skipped) and move on.\n"
     "The counter gets a Datadog monitor to #cards-servicing.\n\n"
     "Refs: CSERV-342",
     (
         F(f"{TXN_PKG}/kafka/KafkaErrorHandlingConfig.kt"),
         S(TXN_YML,
           "      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer\n"
           "      max-poll-records: 500\n"
           "      properties:\n"
           "        specific.avro.reader: true\n",
           "      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer\n"
           "      max-poll-records: 500\n"
           "      properties:\n"
           "        spring.deserializer.value.delegate.class: io.confluent.kafka.serializers.KafkaAvroDeserializer\n"
           "        specific.avro.reader: true\n"),
     )),
    ("2023-08-21 15:40", "mateo.rossi",
     "chore: Spring Boot 3.1 and Kotlin 1.9\n\n"
     "Spring Boot 2.6 is out of OSS support. Nothing here imports javax.*, so\n"
     "the only visible change is the statsd export properties, which moved to\n"
     "management.statsd.metrics.export.* in Boot 3.",
     (
         S(TXN_GRADLE, TXN_PLUGINS_2022, TXN_PLUGINS_2023),
         S(TXN_GRADLE, 'val confluentVersion = "7.1.1"', 'val confluentVersion = "7.4.1"'),
         S(TXN_GRADLE, 'implementation("org.apache.avro:avro:1.11.0")', 'implementation("org.apache.avro:avro:1.11.2")'),
         S(TXN_YML,
           "  metrics:\n    export:\n      statsd:\n        flavor: datadog\n",
           "  statsd:\n    metrics:\n      export:\n        flavor: datadog\n"),
     )),
    ("2024-02-05 10:05", "mateo.rossi",
     "feat: keep merchant country and channel for the transaction detail screen\n\n"
     "Digital Channels' new detail screen shows where and how the card was used\n"
     "(DIG-574). Both come straight from the authorisation event (country,\n"
     "channel). The columns are nullable and older rows are not backfilled:\n"
     "they leave the app's 13-month window on their own.\n\n"
     "Refs: CSERV-415",
     (
         F("src/main/resources/db/migration/V2__merchant_country_and_channel.sql"),
         S(TXN_MODEL, "    val currency: String,\n    val status: TransactionStatus,",
           "    val currency: String,\n    val merchantCountry: String,\n    val channel: String,\n"
           "    val status: TransactionStatus,"),
         S(TXN_MODEL, "        currency = currency,\n        status = TransactionStatus.PENDING,",
           "        currency = currency,\n        merchantCountry = country,\n        channel = channel,\n"
           "        status = TransactionStatus.PENDING,"),
         S(TXN_REPO, '        .addValue("currency", currency)\n        .addValue("status", status.name)',
           '        .addValue("currency", currency)\n        .addValue("merchantCountry", merchantCountry)\n'
           '        .addValue("channel", channel)\n        .addValue("status", status.name)'),
         S(TXN_REPO,
           "            INSERT INTO card_transaction (auth_id, card_token, merchant_id, amount, currency,\n"
           "                                          status, authorised_at, source_partition, source_offset)\n"
           "            VALUES (:authId, :cardToken, :merchantId, :amount, :currency,\n"
           "                    :status, :authorisedAt, :sourcePartition, :sourceOffset)\n",
           final(TXN, TXN_REPO, "            INSERT INTO card_transaction", ":sourcePartition, :sourceOffset)\n")),
         S(TXN_REPO,
           "            SELECT auth_id, card_token, merchant_id, amount, currency, status,\n"
           "                   authorised_at, source_partition, source_offset\n"
           "              FROM card_transaction\n"
           "             WHERE card_token = :cardToken\n",
           "            SELECT auth_id, card_token, merchant_id, amount, currency, merchant_country,\n"
           "                   channel, status, authorised_at, source_partition, source_offset\n"
           "              FROM card_transaction\n"
           "             WHERE card_token = :cardToken\n"),
         S(TXN_REPO, '                currency = rs.getString("currency"),\n                status = ',
           '                currency = rs.getString("currency"),\n'
           '                merchantCountry = rs.getString("merchant_country") ?: "",\n'
           '                channel = rs.getString("channel") ?: "",\n                status = '),
         S(TXN_TEST, '        assertEquals(BigDecimal("1530"), tx.amount)\n    }\n}\n',
           final(TXN, TXN_TEST, '        assertEquals(BigDecimal("1530"), tx.amount)', "    }\n}\n")),
     )),
    ("2024-10-28 09:50", "mateo.rossi",
     "chore: Java 21, Kotlin 2.0 and Spring Boot 3.3\n\n"
     "Java 21 is the platform base image since PLAT-388. Kotlin 2.0 deprecates\n"
     "kotlinOptions, so the compiler flags move to kotlin.compilerOptions.\n"
     "Flyway 10 ships database support separately, hence\n"
     "flyway-database-postgresql. CI moves to setup-gradle v4 and\n"
     "upload-artifact v4.",
     (
         S(TXN_GRADLE, "import org.jetbrains.kotlin.gradle.tasks.KotlinCompile\n\nplugins {", "plugins {"),
         S(TXN_GRADLE, TXN_PLUGINS_2023, TXN_PLUGINS_2024),
         S(TXN_GRADLE, "java.sourceCompatibility = JavaVersion.VERSION_17\n",
           "java {\n    toolchain {\n        languageVersion = JavaLanguageVersion.of(21)\n    }\n}\n"),
         S(TXN_GRADLE, 'val confluentVersion = "7.4.1"', 'val confluentVersion = "7.7.1"'),
         S(TXN_GRADLE, 'implementation("org.apache.avro:avro:1.11.2")', 'implementation("org.apache.avro:avro:1.11.4")'),
         S(TXN_GRADLE, '    implementation("org.flywaydb:flyway-core")\n',
           '    implementation("org.flywaydb:flyway-core")\n    implementation("org.flywaydb:flyway-database-postgresql")\n'),
         S(TXN_GRADLE,
           "tasks.withType<KotlinCompile> {\n    kotlinOptions {\n"
           '        freeCompilerArgs = listOf("-Xjsr305=strict")\n        jvmTarget = "17"\n    }\n}\n',
           'kotlin {\n    compilerOptions {\n        freeCompilerArgs.addAll("-Xjsr305=strict")\n    }\n}\n'),
         S(".github/workflows/ci.yml", 'java-version: "17"', 'java-version: "21"'),
         S(".github/workflows/ci.yml",
           '      - uses: gradle/gradle-build-action@v2\n        with:\n          gradle-version: "7.4.2"\n',
           '      - uses: gradle/actions/setup-gradle@v4\n        with:\n          gradle-version: "8.10.2"\n'),
         S(".github/workflows/ci.yml", "actions/upload-artifact@v3", "actions/upload-artifact@v4"),
     )),
    ("2025-01-13 08:12", "platform-bot",
     "chore(deps): bump org.springframework.boot from 3.3.5 to 3.4.1",
     (S(TXN_GRADLE, 'id("org.springframework.boot") version "3.3.5"', 'id("org.springframework.boot") version "3.4.1"'),)),
    ("2025-04-14 14:25", "mateo.rossi",
     "perf: batch listener, one JDBC batch per poll\n\n"
     "Postgres write IOPS were the bottleneck at the Saturday peak: one INSERT\n"
     "round trip per authorisation. The listener now receives each poll (up to\n"
     "max.poll.records=500) and writes it with a single batchUpdate; offsets\n"
     "for the batch commit after the write. A record that cannot be read is\n"
     "reported with its index (BatchListenerFailedException), so the error\n"
     "handler still skips exactly that record.\n\n"
     "Saturday-peak replay in uat: max lag 41k -> 3k.\n\n"
     "Refs: CSERV-488",
     (
         S(TXN_LISTENER,
           "import org.springframework.kafka.annotation.KafkaListener\nimport org.springframework.stereotype.Component",
           "import org.springframework.kafka.annotation.KafkaListener\n"
           "import org.springframework.kafka.listener.BatchListenerFailedException\n"
           "import org.springframework.stereotype.Component"),
         S(TXN_LISTENER,
           '    private val ignoredTier = meterRegistry.counter("txn_history.transactions.ignored", "reason", "tier")\n',
           '    private val ignoredTier = meterRegistry.counter("txn_history.transactions.ignored", "reason", "tier")\n'
           '    private val batchSize = meterRegistry.summary("txn_history.batch.size")\n'),
         S(TXN_LISTENER, TXN_RECORD_LISTENER_TIER,
           final(TXN, TXN_LISTENER, "    @KafkaListener(", "transactions.size, records.size)\n    }\n")),
         S(TXN_REPO,
           "    /** Idempotent: replays and rebalances are no-ops thanks to the PK. */\n"
           "    fun upsert(transaction: CardTransaction) {\n"
           "        jdbc.update(UPSERT, transaction.toParams())\n"
           "    }\n",
           final(TXN, TXN_REPO, "    /** One JDBC batch per poll.", "    }\n")),
         S(TXN_YML, "    listener:\n      ack-mode: record\n",
           "    listener:\n      type: batch\n      ack-mode: batch\n"),
     )),
    ("2025-11-17 11:00", "chloe.dubois",
     "feat(api): look up a single transaction by auth_id\n\n"
     "Risk Platform's fraud-case-management only gets an auth_id on\n"
     "fraud.score.computed.v1 and needs the card behind it to open a case\n"
     "(RISK-611). Read-only lookup on the primary key; the history endpoint\n"
     "moves under the same /v1 controller.\n\n"
     "Refs: CSERV-560",
     (
         F(TXN_API),
         S(TXN_REPO, "    private fun CardTransaction.toParams() = MapSqlParameterSource()",
           final(TXN, TXN_REPO, "    fun findByAuthId(", "    private fun CardTransaction.toParams() = MapSqlParameterSource()")),
         S(TXN_REPO, "        private val ROW_MAPPER = RowMapper",
           final(TXN, TXN_REPO, "        private val FIND_BY_AUTH_ID", "        private val ROW_MAPPER = RowMapper")),
     )),
    ("2026-02-09 16:20", "mateo.rossi",
     "feat(api): keyset pagination on authorised_at\n\n"
     "OFFSET paging got slow for heavy users: page 40 of a business card took\n"
     "900 ms. Page by authorised_at instead (?before=<last item's\n"
     "authorisedAt>), which uses the (card_token, authorised_at) index all the\n"
     "way. Both BFFs moved to the cursor in DIG-702; the page parameter is gone.\n\n"
     "Refs: CSERV-597",
     (
         S(TXN_API,
           "import com.dss26.cards.txnhistory.history.CardTransactionRepository\nimport org.springframework.http.ResponseEntity",
           "import com.dss26.cards.txnhistory.history.CardTransactionRepository\n"
           "import org.springframework.format.annotation.DateTimeFormat\nimport org.springframework.http.ResponseEntity"),
         S(TXN_API, "import org.springframework.web.bind.annotation.RestController\n\n@RestController",
           "import org.springframework.web.bind.annotation.RestController\nimport java.time.Instant\n\n"
           "data class TransactionPage(val items: List<CardTransaction>, val nextBefore: Instant?)\n\n@RestController"),
         S(TXN_API,
           "    fun list(\n"
           "        @PathVariable cardToken: String,\n"
           '        @RequestParam(defaultValue = "0") page: Int,\n'
           '        @RequestParam(defaultValue = "50") size: Int,\n'
           "    ): List<CardTransaction> = repository.findByCard(cardToken, page, size.coerceIn(1, 200))\n",
           final(TXN, TXN_API, "    fun list(", "        return TransactionPage(items, next)\n    }\n")),
         S(TXN_REPO, "import java.sql.Timestamp\n", "import java.sql.Timestamp\nimport java.time.Instant\n"),
         S(TXN_REPO,
           "    fun findByCard(cardToken: String, page: Int, size: Int): List<CardTransaction> =\n"
           "        jdbc.query(\n"
           "            FIND_BY_CARD,\n"
           "            MapSqlParameterSource()\n"
           '                .addValue("cardToken", cardToken)\n'
           '                .addValue("limit", size)\n'
           '                .addValue("offset", page * size),\n',
           final(TXN, TXN_REPO, "    fun findByCard(", '                .addValue("limit", limit),\n')),
         S(TXN_REPO,
           "             WHERE card_token = :cardToken\n"
           "             ORDER BY authorised_at DESC\n"
           "             LIMIT :limit OFFSET :offset\n",
           "             WHERE card_token = :cardToken\n"
           "               AND (CAST(:before AS timestamptz) IS NULL OR authorised_at < CAST(:before AS timestamptz))\n"
           "             ORDER BY authorised_at DESC\n"
           "             LIMIT :limit\n"),
     )),
    ("2026-06-22 10:40", "chloe.dubois",
     "docs: runbook, and a README that matches the service again\n\n"
     "The README still described the 2022 record listener. Rewritten around\n"
     "what runs today, with the dashboards, monitors and on-call position, and\n"
     "a runbook for lag, skipped records and replaying a time range.",
     (F("README.md"), F("docs/runbook.md"))),
)

TXN_YML_FETCH_OLD = "        fetch.min.bytes: 1\n        fetch.max.wait.ms: 500\n"

TXN_PRS = (
    ScenarioPR(
        key="txn-history-fetch-batching",
        kind="decoy",
        scenario="consumer-lag",
        branch="mateo/txn-history-fetch-batching",
        title="perf(consumer): fetch fuller batches from cards.authorisation.requested.v1",
        body=(
            "## What\n"
            "Raise `fetch.min.bytes` from 1 byte to 64 KiB and `fetch.max.wait.ms` from 500 to 1000 "
            "on the `txn-history-builder` consumer.\n\n"
            "## Why\n"
            "Since the batch listener (CSERV-488) every poll becomes one JDBC batch, but off-peak the "
            "broker answers each fetch as soon as a single record is there, so we write batches of 1-5 "
            "rows. Asking the broker to wait for 64 KiB (or 1 s, whichever comes first) gives us batches "
            "of a few hundred rows and roughly a third of the Postgres write IOPS off-peak. Worst case "
            "a transaction reaches the app history up to 1 s later.\n\n"
            "Only this consumer group is affected (`txn-history-builder`); no change to offsets, "
            "commits or deserialisation.\n\n"
            "## Testing\n"
            "uat for two days: p50 batch size 3 -> 210, write IOPS -34%, lag unchanged.\n\n"
            "Refs: CSERV-612"
        ),
        author="mateo.rossi",
        commit_message=(
            "perf(consumer): fetch fuller batches from cards.authorisation.requested.v1\n\n"
            "fetch.min.bytes 1 -> 65536 and fetch.max.wait.ms 500 -> 1000, so\n"
            "off-peak polls fill the JDBC batch instead of writing a few rows at a\n"
            "time. Adds at most 1 s before a transaction shows in the app.\n\n"
            "Refs: CSERV-612"
        ),
        ops=(Edit(TXN_YML, TXN_YML_FETCH_OLD,
                  "        # Let the broker fill a fetch so each poll is a decent JDBC batch (CSERV-612).\n"
                  "        fetch.min.bytes: 65536\n        fetch.max.wait.ms: 1000\n"),),
        labels=("performance", "kafka"),
    ),
)

TXN_SPEC = RepoSpec(
    name=TXN,
    description="Cardholder transaction history for the apps, built from cards.authorisation.requested.v1.",
    team="cards-servicing",
    domain="cards",
    tier="B",
    topics=("team-cards-servicing", "domain-cards", "kotlin", "spring-boot", "kafka", "postgres"),
    history=TXN_HISTORY,
    prs=TXN_PRS,
    labels=DEFAULT_LABELS + (L_KAFKA, L_PERF),
)

# ===========================================================================
# Tier B - merchant-analytics-stream (payments-edge, Java Kafka Streams)
# ===========================================================================

MAS = "merchant-analytics-stream"
MAS_PKG = "src/main/java/com/dss26/payments/analytics"
MAS_AGG = f"{MAS_PKG}/KpiAggregator.java"
MAS_TOPO = f"{MAS_PKG}/MerchantKpiTopology.java"
MAS_CFG = f"{MAS_PKG}/StreamsConfigFactory.java"
MAS_APP = f"{MAS_PKG}/MerchantAnalyticsApp.java"
MAS_KPI = "src/main/avro/internal/MerchantKpi.avsc"
MAS_TEST = "src/test/java/com/dss26/payments/analytics/KpiAggregatorTest.java"
MAS_DOCS = "docs/kpis.md"
MAS_VALUES = "deploy/values-prod.yaml"

MAS_CATALOG = catalog_info(
    MAS,
    title="Merchant analytics stream",
    description="Windowed merchant KPIs (volume, value, channel mix, risk-flagged share) from card authorisations.",
    owner="payments-edge", system="merchant-acquiring",
    tags=("java", "kafka-streams", "kafka", "tier-3"),
    dashboard=dd("p7m-2rw-c4h", MAS),
    consumes=(AUTH_TOPIC,), groups=(MAS,),
    depends_on=("component:merchant-gateway",),
)

MAS_CODEOWNERS = """\
* @dss26-org/payments-edge
"""

MAS_README_2022 = """\
# merchant-analytics-stream

Merchant KPIs for the merchant portal, computed with Kafka Streams from
`cards.authorisation.requested.v1` (application.id `merchant-analytics-stream`):
authorisation count, requested value per currency and largest ticket per
merchant, in 5-minute windows.

## Build

```bash
mvn -B verify
```

## Run

Needs `KAFKA_BOOTSTRAP_SERVERS`, `SCHEMA_REGISTRY_URL` and, outside a laptop,
`KAFKA_USERNAME` / `KAFKA_PASSWORD`.

## Owners

Payments Edge, `#payments-edge`.
"""

_MAS_PROPS = """\
    <maven.compiler.release>{release}</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <kafka.version>{kafka}</kafka.version>
    <confluent.version>{confluent}</confluent.version>
    <avro.version>{avro}</avro.version>
{jackson}    <slf4j.version>{slf4j}</slf4j.version>
    <logback.version>{logback}</logback.version>
    <junit.version>{junit}</junit.version>
"""
MAS_PROPS_2022 = _MAS_PROPS.format(release=17, kafka="3.2.3", confluent="7.2.2", avro="1.11.1", jackson="",
                                   slf4j="2.0.3", logback="1.4.4", junit="5.9.1")
MAS_PROPS_2024 = _MAS_PROPS.format(release=21, kafka="3.6.1", confluent="7.6.0", avro="1.11.3", jackson="",
                                   slf4j="2.0.11", logback="1.4.14", junit="5.10.1")
MAS_PROPS_2024_IQ = _MAS_PROPS.format(release=21, kafka="3.6.1", confluent="7.6.0", avro="1.11.3",
                                      jackson="    <jackson.version>2.17.0</jackson.version>\n",
                                      slf4j="2.0.11", logback="1.4.14", junit="5.10.1")
MAS_PROPS_2025 = final(MAS, "pom.xml", "    <maven.compiler.release>", "</junit.version>\n")

MAS_JACKSON_DEP = final(MAS, "pom.xml", "    <dependency>\n      <groupId>com.fasterxml.jackson.core</groupId>",
                        "    </dependency>\n")


def _plugin(artifact: str, version: str) -> str:
    return f"<artifactId>{artifact}</artifactId>\n        <version>{version}</version>"


MAS_HISTORY = history(
    MAS,
    ("2022-10-03 09:47", "ravi.iyer",
     "feat: merchant KPIs from cards.authorisation.requested.v1 (Kafka Streams)\n\n"
     "The merchant portal shows yesterday's numbers from the clearing files.\n"
     "This application re-keys authorisation requests by merchant_id and keeps\n"
     "5-minute tumbling windows (count, requested value per currency, largest\n"
     "ticket) in a window store, so the portal can show today as it happens.\n\n"
     "application.id merchant-analytics-stream; tier=prod records only.\n\n"
     "Refs: PAY-412",
     (
         Write("README.md", MAS_README_2022),
         Write("catalog-info.yaml", MAS_CATALOG),
         Write(".github/CODEOWNERS", MAS_CODEOWNERS),
         F(".github/workflows/ci.yml"),
         Write(".gitignore", GITIGNORE_MAVEN),
         F("pom.xml"),
         Write(f"src/main/avro/{AUTH_TOPIC}.avsc", AUTH_V1_AVSC),
         F(MAS_KPI),
         F(MAS_AGG),
         F(MAS_TOPO),
         F(MAS_CFG),
         F(MAS_APP),
         F(MAS_TEST),
         F(MAS_VALUES),
     )),
    ("2022-10-19 15:02", "marta.silva",
     "docs: KPI definitions agreed with the merchant portal team\n\n"
     "Requests, not approvals; no currency conversion; UTC windows. Written\n"
     "down so the portal and acquiring ops stop comparing different numbers.",
     (F(MAS_DOCS),)),
    ("2023-01-30 11:12", "ravi.iyer",
     "chore(deploy): run against cards-prod-euw1\n\n"
     "kafka-dc1 exit. The changelog topics were mirrored with the input topic,\n"
     "so the stores restore on the new cluster instead of starting empty;\n"
     "expect about 20 minutes of restoration after the cutover before the\n"
     "portal's numbers catch up.\n\n"
     "Refs: PLAT-212",
     (S(MAS_VALUES, "      name: kafka-dc1\n", "      name: kafka-cards-prod-euw1\n"),)),
    ("2023-05-08 10:26", "ravi.iyer",
     "feat: hourly windows and channel mix\n\n"
     "Acquiring ops want the hourly view for the daily call, and the portal\n"
     "wants the e-commerce share per merchant. Second window store at 1 hour\n"
     "on the same grouped stream (no second repartition), plus a\n"
     "channel_counts map on MerchantKpi. The field has a default, so the\n"
     "existing changelog data still reads.\n\n"
     "Refs: PAY-466",
     (
         S(MAS_TOPO, '    public static final String STORE_5M = "merchant-kpi-5m";\n',
           '    public static final String STORE_5M = "merchant-kpi-5m";\n'
           '    public static final String STORE_1H = "merchant-kpi-1h";\n'),
         S(MAS_TOPO, "        windowed(byMerchant, Duration.ofMinutes(5), STORE_5M, kpiSerde);\n",
           "        windowed(byMerchant, Duration.ofMinutes(5), STORE_5M, kpiSerde);\n"
           "        windowed(byMerchant, Duration.ofHours(1), STORE_1H, kpiSerde);\n"),
         S(MAS_AGG, "                .setMaxAmount(0.0)\n",
           "                .setMaxAmount(0.0)\n                .setChannelCounts(new HashMap<>())\n"),
         S(MAS_AGG, "        amounts.merge(auth.getCurrency(), auth.getAmount(), Double::sum);\n\n",
           "        amounts.merge(auth.getCurrency(), auth.getAmount(), Double::sum);\n\n"
           "        Map<String, Long> channels = new HashMap<>(kpi.getChannelCounts());\n"
           "        channels.merge(auth.getChannel(), 1L, Long::sum);\n\n"),
         S(MAS_AGG, "                .setMaxAmount(Math.max(kpi.getMaxAmount(), auth.getAmount()))\n",
           "                .setMaxAmount(Math.max(kpi.getMaxAmount(), auth.getAmount()))\n"
           "                .setChannelCounts(channels)\n"),
         S(MAS_KPI, '"doc": "Largest single request in the window, any currency."}\n',
           final(MAS, MAS_KPI, '"doc": "Largest single request in the window, any currency."}',
                 'RECURRING, MOTO)."}') + "\n"),
         S(MAS_TEST, "        assertEquals(30.0, kpi.getMaxAmount(), 1e-9);\n    }\n}\n",
           final(MAS, MAS_TEST, "        assertEquals(30.0, kpi.getMaxAmount(), 1e-9);",
                 'kpi.getChannelCounts().get("RECURRING"));\n    }\n') + "}\n"),
         S(MAS_DOCS, "dropped and counted in the `dropped-records` Streams metric.\n",
           final(MAS, MAS_DOCS, "dropped and counted in the `dropped-records`", "e-commerce share.\n")),
     )),
    ("2023-11-20 14:48", "marta.silva",
     "fix: exactly-once processing for the KPI stores\n\n"
     "After each broker rolling restart the portal showed a few merchants with\n"
     "inflated counts: at-least-once replays everything since the last commit\n"
     "into the window stores. Switch to exactly_once_v2 (brokers are on 3.x)\n"
     "and commit every second rather than the EOS default of 100 ms.\n\n"
     "Refs: PAY-519",
     (
         S(MAS_CFG, "        p.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, StreamsConfig.AT_LEAST_ONCE);\n",
           "        p.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, StreamsConfig.EXACTLY_ONCE_V2);\n"
           "        p.put(StreamsConfig.COMMIT_INTERVAL_MS_CONFIG, 1000);\n"),
         F("src/test/java/com/dss26/payments/analytics/StreamsConfigFactoryTest.java"),
     )),
    ("2024-01-22 09:35", "ravi.iyer",
     "chore: Java 21, Kafka Streams 3.6 and Confluent 7.6\n\n"
     "cache.max.bytes.buffering is deprecated since 3.4; same value under\n"
     "statestore.cache.max.bytes.",
     (
         S("pom.xml", MAS_PROPS_2022, MAS_PROPS_2024),
         S("pom.xml", _plugin("maven-surefire-plugin", "3.0.0-M7"), _plugin("maven-surefire-plugin", "3.2.5")),
         S("pom.xml", _plugin("maven-shade-plugin", "3.4.0"), _plugin("maven-shade-plugin", "3.5.1")),
         S(MAS_CFG, "        p.put(StreamsConfig.CACHE_MAX_BYTES_BUFFERING_CONFIG, 64L * 1024 * 1024);\n",
           "        p.put(StreamsConfig.STATESTORE_CACHE_MAX_BYTES_CONFIG, 64L * 1024 * 1024);\n"),
         S(".github/workflows/ci.yml", 'java-version: "17"', 'java-version: "21"'),
     )),
    ("2024-04-15 13:55", "noah.becker",
     "feat(api): serve merchant KPIs to the portal over interactive queries\n\n"
     "The portal BFF polled a nightly export. It now calls\n"
     "GET /merchants/{id}/kpis?window=5m|1h on any instance; the instance that\n"
     "does not own the merchant's partition answers 307 with the owner's\n"
     "address (application.server = pod DNS name). No new topic, no new store.\n\n"
     "Refs: PAY-588",
     (
         F(f"{MAS_PKG}/KpiQueryServer.java"),
         S("pom.xml", MAS_PROPS_2024, MAS_PROPS_2024_IQ),
         S("pom.xml", "    <dependency>\n      <groupId>org.slf4j</groupId>",
           MAS_JACKSON_DEP + "    <dependency>\n      <groupId>org.slf4j</groupId>"),
         S(MAS_CFG, "        p.put(StreamsConfig.STATESTORE_CACHE_MAX_BYTES_CONFIG, 64L * 1024 * 1024);\n",
           "        p.put(StreamsConfig.STATESTORE_CACHE_MAX_BYTES_CONFIG, 64L * 1024 * 1024);\n"
           '        p.put(StreamsConfig.APPLICATION_SERVER_CONFIG, env.getOrDefault("APPLICATION_SERVER", "localhost:8080"));\n'),
         S(MAS_APP, "import org.apache.kafka.streams.KafkaStreams;\nimport org.apache.kafka.streams.Topology;",
           "import org.apache.kafka.streams.KafkaStreams;\nimport org.apache.kafka.streams.StreamsConfig;\n"
           "import org.apache.kafka.streams.Topology;"),
         S(MAS_APP,
           '        Runtime.getRuntime().addShutdownHook(new Thread(() -> streams.close(Duration.ofSeconds(30)), "shutdown"));\n\n'
           "        streams.start();\n",
           final(MAS, MAS_APP, "        String appServer", "        queries.start();\n")),
         S(MAS_VALUES, "  STATE_DIR: /var/lib/merchant-analytics-stream\n",
           final(MAS, MAS_VALUES, "  STATE_DIR: /var/lib/merchant-analytics-stream\n", "  port: 8080\n")),
     )),
    ("2025-01-06 10:10", "ravi.iyer",
     "chore(deps): Kafka Streams 3.8.1, Confluent 7.8.0 and the rest of the stack\n\n"
     "Batched the platform-bot PRs that were waiting on each other (the serde\n"
     "and kafka-streams have to move together).",
     (
         S("pom.xml", MAS_PROPS_2024_IQ, MAS_PROPS_2025),
         S("pom.xml", _plugin("maven-surefire-plugin", "3.2.5"), _plugin("maven-surefire-plugin", "3.5.2")),
         S("pom.xml", _plugin("maven-shade-plugin", "3.5.1"), _plugin("maven-shade-plugin", "3.6.0")),
     )),
    ("2025-06-23 11:40", "noah.becker",
     "feat: risk-flagged share per merchant\n\n"
     "Acquiring ops asked for an early signal of card testing at a merchant:\n"
     "the share of requests that arrive with at least one risk signal. New\n"
     "risk_flagged_count on MerchantKpi (defaulted, so stored windows still\n"
     "read); the portal computes the share.\n\n"
     "Refs: PAY-702",
     (
         S(MAS_AGG, "                .setChannelCounts(new HashMap<>())\n",
           "                .setChannelCounts(new HashMap<>())\n                .setRiskFlaggedCount(0L)\n"),
         S(MAS_AGG, "        channels.merge(auth.getChannel(), 1L, Long::sum);\n\n",
           "        channels.merge(auth.getChannel(), 1L, Long::sum);\n\n"
           "        boolean flagged = auth.getRiskSignals() != null && !auth.getRiskSignals().isEmpty();\n\n"),
         S(MAS_AGG, "                .setChannelCounts(channels)\n",
           "                .setChannelCounts(channels)\n"
           "                .setRiskFlaggedCount(kpi.getRiskFlaggedCount() + (flagged ? 1 : 0))\n"),
         S(MAS_KPI, 'RECURRING, MOTO)."}\n',
           final(MAS, MAS_KPI, 'RECURRING, MOTO)."}', "at least one risk signal.\"}\n")),
         S(MAS_TEST, '        assertEquals(1L, kpi.getChannelCounts().get("RECURRING"));\n    }\n}\n',
           final(MAS, MAS_TEST, '        assertEquals(1L, kpi.getChannelCounts().get("RECURRING"));', "    }\n}\n")),
         S(MAS_DOCS, "The portal shows the e-commerce share.\n",
           final(MAS, MAS_DOCS, "The portal shows the e-commerce share.", "hourly view.\n")),
     )),
    ("2026-02-09 09:58", "ravi.iyer",
     "chore: one standby replica per state store\n\n"
     "A pod restart took the portal's KPIs away for up to 20 minutes while the\n"
     "1h store restored from its changelog. With a warm standby the task moves\n"
     "in seconds. Costs one more copy of the stores on disk.\n\n"
     "Refs: PAY-771",
     (S(MAS_CFG, "NUM_STANDBY_REPLICAS_CONFIG, 0);", "NUM_STANDBY_REPLICAS_CONFIG, 1);"),)),
    ("2026-07-14 14:30", "noah.becker",
     "docs(readme): architecture, alerts and the reset runbook\n\n"
     "The README still described the 2022 version. Adds the internal topics,\n"
     "what to do when the portal shows stale KPIs, and how to reset the\n"
     "application after a topology change.",
     (F("README.md"),)),
)

MAS_SPEC = RepoSpec(
    name=MAS,
    description="Kafka Streams app: per-merchant KPIs from cards.authorisation.requested.v1 for the merchant portal.",
    team="payments-edge",
    domain="payments",
    tier="B",
    topics=("team-payments-edge", "domain-payments", "java", "kafka-streams", "kafka"),
    history=MAS_HISTORY,
    labels=DEFAULT_LABELS + (L_KAFKA,),
)

# ===========================================================================
# Tier B - disputes-svc (cards-servicing, Java)
# ===========================================================================

DSP = "disputes-svc"
DSP_PKG = "src/main/java/com/dss26/cards/disputes"
DSP_APP = f"{DSP_PKG}/DisputesApplication.java"
DSP_CODES = f"{DSP_PKG}/chargeback/ReasonCodes.java"
DSP_REPO = f"{DSP_PKG}/chargeback/ChargebackRepository.java"
DSP_API = f"{DSP_PKG}/api/ChargebackController.java"
DSP_YML = "src/main/resources/application.yml"
DSP_TEMPLATE = "search/index-template.json"
DSP_CODES_TEST = "src/test/java/com/dss26/cards/disputes/chargeback/ReasonCodesTest.java"
DSP_PARENT = "    <artifactId>spring-boot-starter-parent</artifactId>\n    <version>{}</version>"
CHARGEBACK_TOPICS = ("cards.chargeback.opened.v1", "cards.chargeback.resolved.v1")
REFUND_TOPICS = ("cards.refund.requested.v1", "cards.refund.completed.v1")


def _dsp_catalog(*, refunds: bool, pagerduty: bool) -> str:
    return catalog_info(
        DSP,
        title="Disputes (chargebacks and refunds)",
        description="Chargeback cases, representment deadlines and merchant refunds; owns the disputes search mapping.",
        owner="cards-servicing", system="card-servicing",
        tags=("java", "spring-boot", "kafka", "elasticsearch", "tier-1"),
        pagerduty="PSVC8KD" if pagerduty else None,
        opsgenie=None if pagerduty else "Cards Servicing",
        dashboard=dd("v2c-8nf-x7k", DSP),
        consumes=("cards.refund.requested.v1",) if refunds else (),
        produces=CHARGEBACK_TOPICS + (("cards.refund.completed.v1",) if refunds else ()),
        groups=("disputes-svc-refunds",) if refunds else (),
        depends_on=("resource:disputes-db", "resource:disputes-search"),
        links=(ADR_0007,),
    )


DSP_CODEOWNERS = """\
*                 @dss26-org/cards-servicing
# The search mapping is read by the Cards Platform connector; they review it too.
/search/          @dss26-org/cards-servicing @dss26-org/cards-platform
"""

DSP_README_2024 = """\
# disputes-svc

Chargeback cases for DSS26 Bank cards, moved out of the card management
system. Analysts open and resolve cases through the REST API; every case
change is published on `cards.chargeback.opened.v1` and
`cards.chargeback.resolved.v1` (Avro, ADR-0007), keyed by chargeback id.

## Build

```bash
mvn -B verify
```

## On-call

Tier 1. Paging through Opsgenie (team "Cards Servicing").
"""

DSP_HISTORY = history(
    DSP,
    ("2024-01-15 10:02", "chloe.dubois",
     "feat: disputes-svc - chargeback cases out of the card management system\n\n"
     "First slice of the CMS decomposition. Cases, reason-code categories and\n"
     "the case lifecycle move here; the CMS screens stay read-only until the\n"
     "back office switches over. Events go out after the database commit\n"
     "(TransactionalEventListener) so a rolled-back case never reaches Kafka.\n\n"
     "Refs: CSERV-436",
     (
         Write("README.md", DSP_README_2024),
         Write("catalog-info.yaml", _dsp_catalog(refunds=False, pagerduty=False)),
         Write(".github/CODEOWNERS", DSP_CODEOWNERS),
         F(".github/workflows/ci.yml"),
         Write(".gitignore", GITIGNORE_MAVEN),
         F("pom.xml"),
         *avro("src/main/avro", *CHARGEBACK_TOPICS),
         F(DSP_APP),
         F(f"{DSP_PKG}/chargeback/CardNetwork.java"),
         F(DSP_CODES),
         F(f"{DSP_PKG}/chargeback/Chargeback.java"),
         F(DSP_REPO),
         F(f"{DSP_PKG}/chargeback/ChargebackService.java"),
         F(f"{DSP_PKG}/chargeback/ChargebackEventPublisher.java"),
         F(DSP_API),
         F(DSP_YML),
         F("src/main/resources/db/migration/V1__chargeback.sql"),
         F(DSP_CODES_TEST),
     )),
    ("2024-03-11 14:18", "chloe.dubois",
     "feat(refunds): close out merchant refunds from cards.refund.requested.v1\n\n"
     "Second CMS slice. Consumer group disputes-svc-refunds; the refund row and\n"
     "the dedup check share one transaction, so a redelivered request does\n"
     "not credit the cardholder twice.\n\n"
     "Refs: CSERV-449",
     (
         F(f"{DSP_PKG}/refund/RefundRequestListener.java"),
         F("src/main/resources/db/migration/V2__refund.sql"),
         *avro("src/main/avro", *REFUND_TOPICS),
         S(DSP_YML, "        use.latest.version: true\n",
           final(DSP, DSP_YML, "        use.latest.version: true\n", "      ack-mode: record\n")),
         Write("catalog-info.yaml", _dsp_catalog(refunds=True, pagerduty=False)),
     )),
    ("2024-05-13 16:45", "mateo.rossi",
     "feat(search): index template for the chargeback search sink\n\n"
     "Cards Platform is adding sink-elastic-disputes-search (CARDS-1032) to\n"
     "index both chargeback topics. The connector runs with schema.ignore=true,\n"
     "so without a template Elasticsearch guesses the mapping from the first\n"
     "document. This template pins it for cards.chargeback.* and puts both\n"
     "indices behind the disputes-search alias.",
     (
         F(DSP_TEMPLATE),
         F("search/apply-index-template.sh", executable=True),
         S(".github/workflows/ci.yml", "        run: mvn -B -ntp verify\n",
           final(DSP, ".github/workflows/ci.yml", "        run: mvn -B -ntp verify\n", "> /dev/null\n")),
     )),
    ("2024-05-27 11:30", "mateo.rossi",
     "feat(api): back-office search over the disputes-search alias\n\n"
     "Filters by merchant and reason category, newest first. Plain REST\n"
     "against Elasticsearch; the mapping is ours (search/index-template.json),\n"
     "the documents come from the connector.\n\n"
     "Refs: CSERV-467",
     (
         F(f"{DSP_PKG}/search/ChargebackSearch.java"),
         S(DSP_API,
           "import com.dss26.cards.disputes.chargeback.ChargebackService;\nimport com.dss26.cards.events.ChargebackOutcome;",
           "import com.dss26.cards.disputes.chargeback.ChargebackService;\n"
           "import com.dss26.cards.disputes.search.ChargebackSearch;\n"
           "import com.dss26.cards.events.ChargebackOutcome;"),
         S(DSP_API, "import org.springframework.web.bind.annotation.PathVariable;",
           "import org.springframework.web.bind.annotation.GetMapping;\n"
           "import org.springframework.web.bind.annotation.PathVariable;"),
         S(DSP_API,
           "import org.springframework.web.bind.annotation.RequestMapping;\n"
           "import org.springframework.web.bind.annotation.RestController;",
           "import org.springframework.web.bind.annotation.RequestMapping;\n"
           "import org.springframework.web.bind.annotation.RequestParam;\n"
           "import org.springframework.web.bind.annotation.RestController;"),
         S(DSP_API, "import java.math.BigDecimal;\n",
           "import java.math.BigDecimal;\nimport java.util.List;\nimport java.util.Map;\n"),
         S(DSP_API,
           "    private final ChargebackService service;\n\n"
           "    public ChargebackController(ChargebackService service) {\n"
           "        this.service = service;\n"
           "    }\n",
           final(DSP, DSP_API, "    private final ChargebackService service;\n", "        this.search = search;\n    }\n")),
         S(DSP_API, "        return service.resolve(id, req.outcome(), req.recoveredAmount());\n    }\n}\n",
           final(DSP, DSP_API, "        return service.resolve(id, req.outcome(), req.recoveredAmount());\n",
                 "return search.search(merchantId, category, size);\n    }\n}\n")),
         S(DSP_YML, "      ack-mode: record\n\nmanagement:",
           final(DSP, DSP_YML, "      ack-mode: record\n", "\nmanagement:")),
     )),
    ("2024-07-08 10:12", "mateo.rossi",
     "fix(search): map amounts as scaled_float\n\n"
     "Range filters on disputed_amount returned 49.99 for \"under 50\" twice\n"
     "over because of double rounding. scaled_float with a factor of 100 stores\n"
     "cents exactly and halves the index size for those fields. Applied to uat\n"
     "and prod with a rollover of both indices.",
     (
         S(DSP_TEMPLATE,
           '        "disputed_amount":  { "type": "double" },\n'
           '        "recovered_amount": { "type": "double" },\n',
           '        "disputed_amount":  { "type": "scaled_float", "scaling_factor": 100 },\n'
           '        "recovered_amount": { "type": "scaled_float", "scaling_factor": 100 },\n'),
     )),
    ("2024-11-04 08:05", "platform-bot",
     "chore(deps): bump org.springframework.boot:spring-boot-starter-parent from 3.2.1 to 3.3.5",
     (S("pom.xml", DSP_PARENT.format("3.2.1"), DSP_PARENT.format("3.3.5")),)),
    ("2025-01-13 08:09", "platform-bot",
     "chore(deps): bump org.springframework.boot:spring-boot-starter-parent from 3.3.5 to 3.4.1",
     (S("pom.xml", DSP_PARENT.format("3.3.5"), DSP_PARENT.format("3.4.1")),)),
    ("2025-02-17 15:20", "chloe.dubois",
     "feat(reason-codes): map Mastercard 4808, 4831 and 4834\n\n"
     "They were landing in OTHER, which hides them from the authorisation and\n"
     "processing-error dashboards and from the merchant-risk scoring that\n"
     "reads reason_category.\n\n"
     "Refs: CSERV-503",
     (
         S(DSP_CODES,
           '            "4871", ChargebackCategory.FRAUD,             // Chip liability shift\n'
           '            "4853", ChargebackCategory.CONSUMER_DISPUTE,  // Cardholder dispute\n',
           final(DSP, DSP_CODES, '            "4871"', "// Cardholder dispute\n")),
         S(DSP_CODES_TEST,
           '            "MASTERCARD, 4837, FRAUD",\n            "MASTERCARD, 4853, CONSUMER_DISPUTE"',
           final(DSP, DSP_CODES_TEST, '            "MASTERCARD, 4837, FRAUD",', '"MASTERCARD, 4853, CONSUMER_DISPUTE"')),
     )),
    ("2025-05-12 09:40", "chloe.dubois",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired; Cards Servicing moves to PagerDuty with the\n"
     "rest of Cards & Payments. Service PSVC8KD, escalation policy\n"
     "\"Cards Servicing - Primary\".",
     (
         Write("catalog-info.yaml", _dsp_catalog(refunds=True, pagerduty=True)),
         S("README.md", 'Tier 1. Paging through Opsgenie (team "Cards Servicing").',
           'Tier 1. PagerDuty service `PSVC8KD`, escalation policy "Cards Servicing - Primary".'),
     )),
    ("2025-09-15 13:05", "mateo.rossi",
     "feat(deadlines): count open cases close to the representment deadline\n\n"
     "Two Mastercard cases went past second presentment in August because\n"
     "nobody saw them coming. 30 days for Visa, 45 for Mastercard; every 15\n"
     "minutes we publish how many open cases have 5 days or less left\n"
     "(disputes.chargebacks.due_soon), and the analysts' queue sorts on it.\n\n"
     "Refs: CSERV-541",
     (
         F(f"{DSP_PKG}/chargeback/RepresentmentDeadlines.java"),
         F(f"{DSP_PKG}/chargeback/DeadlineWatch.java"),
         F("src/test/java/com/dss26/cards/disputes/chargeback/RepresentmentDeadlinesTest.java"),
         S(DSP_APP, "import org.springframework.context.annotation.Bean;\n\nimport java.time.Clock;",
           "import org.springframework.context.annotation.Bean;\n"
           "import org.springframework.scheduling.annotation.EnableScheduling;\n\nimport java.time.Clock;"),
         S(DSP_APP, "@SpringBootApplication\npublic class", "@SpringBootApplication\n@EnableScheduling\npublic class"),
         S(DSP_REPO, "import java.time.Instant;\nimport java.util.Optional;",
           "import java.time.Instant;\nimport java.util.List;\nimport java.util.Optional;"),
         S(DSP_REPO, "                .optional();\n    }\n}\n",
           final(DSP, DSP_REPO, "                .optional();\n    }\n", "    }\n}\n")),
     )),
    ("2026-05-04 11:25", "chloe.dubois",
     "docs(readme): architecture, events, search ownership and on-call\n\n"
     "Twice this quarter search issues were raised with us that were\n"
     "connector issues, and the other way round. Spell out who owns what\n"
     "between the mapping (us) and sink-elastic-disputes-search (Cards\n"
     "Platform), and where to look first.",
     (F("README.md"),)),
)

DSP_SPEC = RepoSpec(
    name=DSP,
    description="Chargebacks, representment deadlines and merchant refunds; owns the disputes search mapping.",
    team="cards-servicing",
    domain="cards",
    tier="B",
    topics=("team-cards-servicing", "domain-cards", "java", "spring-boot", "kafka", "elasticsearch", "tier-1"),
    history=DSP_HISTORY,
    labels=DEFAULT_LABELS + (L_KAFKA, Label("search", "bfdadc", "Elasticsearch mapping or queries")),
    team_access=(("cards-platform", "triage"),),
)

# ===========================================================================
# Tier B - clearing-settlement-svc (clearing-settlement, Java)
# ===========================================================================

CLR = "clearing-settlement-svc"
CLR_PKG = "src/main/java/com/dss26/cards/clearing"
CLR_TOPICS_JAVA = f"{CLR_PKG}/Topics.java"
CLR_MATCHER = f"{CLR_PKG}/matching/ClearingMatcher.java"
CLR_SCORER = f"{CLR_PKG}/matching/MatchScorer.java"
CLR_SETTLE = f"{CLR_PKG}/settlement/SettlementBatchJob.java"
CLR_YML = "src/main/resources/application.yml"
CLR_SCORER_TEST = "src/test/java/com/dss26/cards/clearing/matching/MatchScorerTest.java"
CLR_CI = ".github/workflows/ci.yml"
CLR_MATCHED_AVSC = "src/main/avro/cards.clearing.matched.v1.avsc"

CLR_OUT_1 = ("cards.clearing.received.v1", "cards.clearing.matched.v1")
CLR_OUT_ALL = CLR_OUT_1 + ("cards.interchange.fee.calculated.v1", "cards.settlement.batch.posted.v1",
                           "ledger.journal.posted.v1")


def _clr_catalog(*, produces: tuple[str, ...], pagerduty: bool) -> str:
    return catalog_info(
        CLR,
        title="Clearing and settlement",
        description="Scheme clearing ingest, authorisation matching, interchange and daily merchant settlement.",
        owner="clearing-settlement", system="card-clearing-settlement",
        tags=("java", "spring-boot", "kafka", "tier-1", "sox"),
        pagerduty="PSVC3WN" if pagerduty else None,
        opsgenie=None if pagerduty else "Clearing & Settlement",
        dashboard=dd("h4t-6zb-m2q", "clearing-settlement"),
        consumes=CLR_OUT_1 if len(produces) > 2 else ("cards.clearing.received.v1",),
        produces=produces,
        groups=("clearing-settlement-matcher", "clearing-settlement-fees") if len(produces) > 2
        else ("clearing-settlement-matcher",),
        depends_on=("resource:clearing-db", "resource:scheme-gateway-mft"),
        links=(ADR_0007,),
    )


CLR_CODEOWNERS = """\
*                  @dss26-org/clearing-settlement
/src/main/avro/    @dss26-org/clearing-settlement @dss26-org/cards-platform
/.github/          @dss26-org/clearing-settlement @dss26-org/platform-engineering
"""

CLR_README_2022 = """\
# clearing-settlement-svc

Streams scheme clearing onto Kafka. Picks up the normalised Visa Base II and
Mastercard IPM presentment files from the MFT share, publishes each
presentment to `cards.clearing.received.v1`, matches it to its authorisation
and publishes the match to `cards.clearing.matched.v1`.

Replaces the nightly clearing batch on the mainframe.

## Build

```bash
mvn -B verify
```

## Owners

Clearing & Settlement, `#clearing-settlement`.
"""

_AMOUNT_DELTA_FIELD = (
    '    {\n'
    '      "name": "amount_delta",\n'
    '      "type": "double",\n'
    '      "doc": "clearing_amount - auth_amount (0.0 for exact matches)."\n'
    '    },\n'
)
_MATCH_CONFIDENCE_HEAD = '    {\n      "name": "match_confidence",'
assert _AMOUNT_DELTA_FIELD + _MATCH_CONFIDENCE_HEAD in avsc("cards.clearing.matched.v1")
CLR_AVSC_WITH_DELTA = _AMOUNT_DELTA_FIELD + _MATCH_CONFIDENCE_HEAD
CLR_JAVA_WITH_DELTA = (
    "                .setClearingAmount(clearing.getAmount())\n"
    "                .setAmountDelta(clearing.getAmount() - authAmount)\n"
    "                .setMatchConfidence("
)
CLR_JAVA_WITHOUT_DELTA = (
    "                .setClearingAmount(clearing.getAmount())\n"
    "                .setMatchConfidence("
)
CLR_PARENT = "    <artifactId>spring-boot-starter-parent</artifactId>\n    <version>{}</version>"

CLR_HISTORY = history(
    CLR,
    ("2022-06-13 09:40", "henrik.larsen",
     "feat: stream scheme clearing onto Kafka\n\n"
     "Replaces the nightly clearing batch on the mainframe. Presentment files\n"
     "from the scheme gateway are ingested every minute instead of once a\n"
     "night, each presentment goes to cards.clearing.received.v1, and the\n"
     "matcher (group clearing-settlement-matcher) pairs it with its\n"
     "authorisation from the issuer authorisation log.\n\n"
     "Exact amount, same card and merchant only for now; everything else goes\n"
     "to the exceptions queue as before.\n\n"
     "Refs: CLR-204",
     (
         Write("README.md", CLR_README_2022),
         Write("catalog-info.yaml", _clr_catalog(produces=CLR_OUT_1, pagerduty=False)),
         Write(".github/CODEOWNERS", CLR_CODEOWNERS),
         F(CLR_CI),
         Write(".gitignore", GITIGNORE_MAVEN),
         F("pom.xml"),
         *avro("src/main/avro", *CLR_OUT_1),
         F(f"{CLR_PKG}/ClearingSettlementApplication.java"),
         F(CLR_TOPICS_JAVA),
         F(f"{CLR_PKG}/ingest/ClearingFileIngestor.java"),
         F(CLR_SCORER),
         F(f"{CLR_PKG}/matching/AuthorisationLog.java"),
         F(CLR_MATCHER),
         F(CLR_YML),
         F("src/main/resources/db/migration/V1__clearing.sql"),
         F(CLR_SCORER_TEST),
     )),
    ("2022-09-05 10:55", "henrik.larsen",
     "feat(fees): interchange and scheme fees per cleared transaction\n\n"
     "Group clearing-settlement-fees reads cards.clearing.matched.v1 and\n"
     "publishes the fee breakdown to cards.interchange.fee.calculated.v1:\n"
     "IFR caps inside the EEA, the 2019 commitment rates for inter-regional\n"
     "consumer cards, scheme table rate for commercial cards.\n\n"
     "Refs: CLR-231",
     (
         F(f"{CLR_PKG}/fees/CardProduct.java"),
         F(f"{CLR_PKG}/fees/InterchangeCalculator.java"),
         F(f"{CLR_PKG}/fees/FeeListener.java"),
         F("src/main/resources/db/migration/V2__fees.sql"),
         *avro("src/main/avro", "cards.interchange.fee.calculated.v1"),
         S(CLR_TOPICS_JAVA, '    public static final String CLEARING_MATCHED = "cards.clearing.matched.v1";\n',
           '    public static final String CLEARING_MATCHED = "cards.clearing.matched.v1";\n'
           '    public static final String INTERCHANGE_FEE = "cards.interchange.fee.calculated.v1";\n'),
     )),
    ("2023-02-20 14:10", "henrik.larsen",
     "feat(settlement): daily merchant settlement and its GL journal\n\n"
     "Cut-off at 22:00 Paris time on weekdays: one batch per merchant and\n"
     "currency over everything cleared since the last cut-off, published to\n"
     "cards.settlement.batch.posted.v1, plus the journal (scheme clearing ->\n"
     "merchant payable) on ledger.journal.posted.v1. The journal schema\n"
     "belongs to Cards Platform; we use the latest registered version.\n\n"
     "Refs: CLR-266",
     (
         F(CLR_SETTLE),
         F("src/main/resources/db/migration/V3__settlement.sql"),
         *avro("src/main/avro", "cards.settlement.batch.posted.v1", "ledger.journal.posted.v1"),
         S(CLR_TOPICS_JAVA, '    public static final String INTERCHANGE_FEE = "cards.interchange.fee.calculated.v1";\n',
           '    public static final String INTERCHANGE_FEE = "cards.interchange.fee.calculated.v1";\n'
           '    public static final String SETTLEMENT_BATCH = "cards.settlement.batch.posted.v1";\n'
           '    public static final String LEDGER_JOURNAL = "ledger.journal.posted.v1";\n'),
         Write("catalog-info.yaml", _clr_catalog(produces=CLR_OUT_ALL, pagerduty=False)),
     )),
    ("2024-06-24 15:30", "amara.nwosu",
     "test(fees): pin the IFR caps and the inter-regional rates\n\n"
     "The calculator had no tests. These pin the regulatory numbers so a\n"
     "refactor cannot move them silently.",
     (F("src/test/java/com/dss26/cards/clearing/fees/InterchangeCalculatorTest.java"),)),
    ("2024-09-11 11:05", "amara.nwosu",
     "refactor(matching): drop amount_delta from ClearingMatched\n\n"
     "amount_delta is clearing_amount - auth_amount, and both are on the\n"
     "record, so every consumer can compute it. One field less to keep\n"
     "consistent in the matcher.\n\n"
     "Refs: CLR-388",
     (
         S(CLR_MATCHED_AVSC, CLR_AVSC_WITH_DELTA, _MATCH_CONFIDENCE_HEAD),
         S(CLR_MATCHER, CLR_JAVA_WITH_DELTA, CLR_JAVA_WITHOUT_DELTA),
     )),
    ("2024-09-12 09:20", "henrik.larsen",
     "revert(matching): restore amount_delta on ClearingMatched\n\n"
     "INC-2024-09-12-003. Consumers of cards.clearing.matched.v1 that still\n"
     "read with the previous schema failed on the first record without\n"
     "amount_delta (no default), and clearing stopped downstream. Putting\n"
     "the field back; the version without it is soft-deleted in the registry.\n"
     "A field on a .v1 topic stays until the topic is versioned.",
     (
         S(CLR_MATCHED_AVSC, _MATCH_CONFIDENCE_HEAD, CLR_AVSC_WITH_DELTA),
         S(CLR_MATCHER, CLR_JAVA_WITHOUT_DELTA, CLR_JAVA_WITH_DELTA),
     )),
    ("2024-10-15 10:40", "henrik.larsen",
     "ci: run the shared schema-compat check on every pull request\n\n"
     "Action item from INC-2024-09-12-003: every cards repo checks its\n"
     "subjects against the registry before merge, using the reusable\n"
     "workflow from cards-ci-workflows. The ledger journal subject is owned\n"
     "and checked by Cards Platform.",
     (
         S(CLR_CI, "        run: mvn -B -ntp verify\n",
           final(CLR, CLR_CI, "        run: mvn -B -ntp verify\n", "cards.settlement.batch.posted.v1.avsc\n")),
         S(CLR_YML, "        # Schemas are registered by the release pipeline, not at runtime.\n",
           "        # Schemas are registered through CI (schema-compat), not at runtime.\n"),
     )),
    ("2025-03-10 09:15", "amara.nwosu",
     "chore: Spring Boot 3.4 and Java 21\n\n"
     "Off Boot 2.7, whose extended support ends this year. No javax imports\n"
     "to migrate; Flyway 10 needs flyway-database-postgresql. Confluent\n"
     "serializers to 7.8 to match the Kafka 3.8 clients Boot now manages.\n\n"
     "Refs: CLR-412",
     (
         S("pom.xml", CLR_PARENT.format("2.7.0"), CLR_PARENT.format("3.4.1")),
         S("pom.xml", "<java.version>17</java.version>", "<java.version>21</java.version>"),
         S("pom.xml", "<confluent.version>7.1.1</confluent.version>", "<confluent.version>7.8.0</confluent.version>"),
         S("pom.xml", "<avro.version>1.11.0</avro.version>", "<avro.version>1.11.4</avro.version>"),
         S("pom.xml", "      <artifactId>flyway-core</artifactId>", "      <artifactId>flyway-database-postgresql</artifactId>"),
         S(CLR_CI, 'java-version: "17"', 'java-version: "21"'),
     )),
    ("2025-05-19 10:00", "henrik.larsen",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired. Service PSVC3WN, escalation policy\n"
     "\"Clearing & Settlement - Primary\"; same three paging monitors.",
     (Write("catalog-info.yaml", _clr_catalog(produces=CLR_OUT_ALL, pagerduty=True)),)),
    ("2025-06-16 14:35", "amara.nwosu",
     "feat(matching): 15% tolerance for hotels, car hire, restaurants and bars\n\n"
     "Tips and incidentals mean the cleared amount legitimately differs from\n"
     "the authorisation for MCCs 7011, 7512, 5812 and 5813. They made up 61%\n"
     "of the exceptions queue. Inside the tolerance the score scales from\n"
     "0.95 down to the 0.8 threshold; everything else still needs an exact\n"
     "amount.\n\n"
     "Refs: CLR-431",
     (
         S(CLR_SCORER, "import java.math.RoundingMode;\n", "import java.math.RoundingMode;\nimport java.util.Set;\n"),
         S(CLR_SCORER,
           '    static final BigDecimal DEFAULT_TOLERANCE = new BigDecimal("0.00");\n'
           "    public static final double MATCH_THRESHOLD = 0.8;\n",
           final(CLR, CLR_SCORER, "    /** Hotels, car hire", "MATCH_THRESHOLD = 0.8;\n")),
         S(CLR_SCORER, "        BigDecimal tolerance = DEFAULT_TOLERANCE;\n",
           "        BigDecimal tolerance = TOLERANT_MCCS.contains(p.mcc()) ? HOSPITALITY_TOLERANCE : DEFAULT_TOLERANCE;\n"),
         S(CLR_SCORER_TEST, "    @Test\n    void differentCardNeverMatches()",
           final(CLR, CLR_SCORER_TEST, "    @Test\n    void restaurantTipWithinFifteenPercentMatches",
                 "    void differentCardNeverMatches()")),
     )),
    ("2026-01-12 11:45", "henrik.larsen",
     "fix(settlement): no settlement run on TARGET closing days\n\n"
     "On Good Friday the cut-off ran, the batches were posted, and Treasury\n"
     "had to hold the funding file by hand because T2 was closed. The job\n"
     "now skips weekends, 1 January, Good Friday, Easter Monday, 1 May and\n"
     "25/26 December; the next business day's run picks everything up.\n\n"
     "Refs: CLR-470",
     (
         F(f"{CLR_PKG}/settlement/TargetCalendar.java"),
         F("src/test/java/com/dss26/cards/clearing/settlement/TargetCalendarTest.java"),
         S(CLR_SETTLE, "        LocalDate settlementDate = LocalDate.now(clock.withZone(PARIS));\n",
           final(CLR, CLR_SETTLE, "        LocalDate settlementDate", "            return;\n        }\n")),
     )),
    ("2026-08-24 16:10", "amara.nwosu",
     "docs: runbook, README refresh, and a way to re-run the cut-off\n\n"
     "Re-running a failed cut-off meant restarting a pod at the right minute.\n"
     "POST /admin/settlement/run (internal ingress, clearing-ops role) runs\n"
     "it now; it only picks up records that are not settled yet. README\n"
     "rewritten around the full flow, with the schema-change rules.\n\n"
     "Refs: CLR-503",
     (
         F(f"{CLR_PKG}/settlement/SettlementAdminController.java"),
         F("docs/runbook.md"),
         F("README.md"),
     )),
)

CLR_SPEC = RepoSpec(
    name=CLR,
    description="Scheme clearing ingest, auth matching, interchange fees and daily merchant settlement.",
    team="clearing-settlement",
    domain="cards",
    tier="B",
    topics=("team-clearing-settlement", "domain-cards", "java", "spring-boot", "kafka", "tier-1"),
    history=CLR_HISTORY,
    labels=DEFAULT_LABELS + (L_KAFKA, L_SCHEMA),
    team_access=(("cards-platform", "triage"),),
)

# ===========================================================================
# Tier B - card-lifecycle-svc (cards-servicing, Kotlin)
# ===========================================================================

CLC = "card-lifecycle-svc"
CLC_PKG = "src/main/kotlin/com/dss26/cards/lifecycle"
CLC_SM = f"{CLC_PKG}/card/CardStateMachine.kt"
CLC_SVC = f"{CLC_PKG}/card/CardService.kt"
CLC_REPO = f"{CLC_PKG}/card/CardRepository.kt"
CLC_TOPICS = f"{CLC_PKG}/events/CardTopics.kt"
CLC_API = f"{CLC_PKG}/api/CardController.kt"
CLC_RISK = f"{CLC_PKG}/risk/RiskLimitListener.kt"
CLC_YML = "src/main/resources/application.yml"
CLC_TEST = "src/test/kotlin/com/dss26/cards/lifecycle/card/CardStateMachineTest.kt"
CLC_GRADLE = "build.gradle.kts"
CARD_TOPICS_3 = ("cards.card.issued.v1", "cards.card.activated.v1", "cards.card.blocked.v1")


def _clc_catalog(*, full: bool) -> str:
    return catalog_info(
        CLC,
        title="Card lifecycle",
        description="System of record for card state (issued, active, blocked, replaced); publishes cards.card.* events.",
        owner="cards-servicing", system="card-servicing",
        tags=("kotlin", "spring-boot", "kafka", "outbox", "tier-2"),
        dashboard=dd("r8d-3vk-q6p", CLC),
        consumes=("risk.limit.breached.v1",) if full else (),
        produces=CARD_TOPICS_3 + (("cards.card.replaced.v1",) if full else ()),
        groups=(CLC,) if full else (),
        depends_on=("resource:card-lifecycle-db",),
    )


CLC_README_2024 = """\
# card-lifecycle-svc

Card state for DSS26 Bank cards, moved out of the card management system:
issue, activate and block. Every change is written with an outbox row in the
same transaction and published on `cards.card.issued.v1`,
`cards.card.activated.v1` or `cards.card.blocked.v1`, keyed by card token.

## Build

```bash
gradle build
```

## Owners

Cards Servicing, `#cards-servicing`.
"""

_CLC_PLUGINS = """\
    id("org.springframework.boot") version "{boot}"
    id("io.spring.dependency-management") version "{depmgmt}"
    id("com.github.davidmc24.gradle.plugin.avro") version "1.9.1"
    kotlin("jvm") version "{kotlin}"
    kotlin("plugin.spring") version "{kotlin}"
"""

CLC_HISTORY = history(
    CLC,
    ("2024-03-04 10:15", "chloe.dubois",
     "feat: card-lifecycle-svc - card state out of the card management system\n\n"
     "Second service of the CMS decomposition after disputes-svc. Owns the\n"
     "card state machine (issue, activate, block) and publishes every change\n"
     "through a transactional outbox, keyed by card token so one card's events\n"
     "stay in order. The CMS keeps a read-only copy until fulfilment moves.\n\n"
     "Refs: CSERV-452",
     (
         Write("README.md", CLC_README_2024),
         Write("catalog-info.yaml", _clc_catalog(full=False)),
         Write(".github/CODEOWNERS", "* @dss26-org/cards-servicing\n"),
         F(".github/workflows/ci.yml"),
         Write(".gitignore", GITIGNORE_GRADLE),
         F("settings.gradle.kts"),
         F(CLC_GRADLE),
         *avro("src/main/avro", *CARD_TOPICS_3),
         F(f"{CLC_PKG}/CardLifecycleApplication.kt"),
         F(CLC_SM),
         F(f"{CLC_PKG}/card/Card.kt"),
         F(CLC_REPO),
         F(CLC_SVC),
         F(f"{CLC_PKG}/events/Outbox.kt"),
         F(CLC_TOPICS),
         F(f"{CLC_PKG}/events/OutboxPublisher.kt"),
         F(CLC_API),
         F(CLC_YML),
         F("src/main/resources/db/migration/V1__card.sql"),
         F(CLC_TEST),
     )),
    ("2024-04-22 11:40", "mateo.rossi",
     "feat: card replacement for lost, stolen, compromised and expired cards\n\n"
     "Replacing blocks the old token for good (REPLACED is final), issues the\n"
     "new one with the same product, and publishes cards.card.replaced.v1 so\n"
     "recurring payments and stored credentials can move to the new card.\n\n"
     "Refs: CSERV-461",
     (
         *avro("src/main/avro", "cards.card.replaced.v1"),
         S(CLC_TOPICS, "import com.dss26.cards.events.CardIssued\nimport org.apache.avro.Schema",
           "import com.dss26.cards.events.CardIssued\nimport com.dss26.cards.events.CardReplaced\n"
           "import org.apache.avro.Schema"),
         S(CLC_TOPICS,
           '        CardBlocked.getClassSchema().fullName to ("cards.card.blocked.v1" to CardBlocked.getClassSchema()),\n',
           '        CardBlocked.getClassSchema().fullName to ("cards.card.blocked.v1" to CardBlocked.getClassSchema()),\n'
           '        CardReplaced.getClassSchema().fullName to ("cards.card.replaced.v1" to CardReplaced.getClassSchema()),\n'),
         S(CLC_SVC, "import com.dss26.cards.events.CardIssued\nimport com.dss26.cards.lifecycle.events.Outbox",
           "import com.dss26.cards.events.CardIssued\nimport com.dss26.cards.events.CardReplaced\n"
           "import com.dss26.cards.events.ReplacementReason\nimport com.dss26.cards.lifecycle.events.Outbox"),
         S(CLC_SVC, "    private fun load(cardToken: String): Card =",
           final(CLC, CLC_SVC, "    @Transactional\n    fun replace(", "        return replacement\n    }\n\n")
           + "    private fun load(cardToken: String): Card ="),
         S(CLC_API, "import com.dss26.cards.events.CardFormFactor\nimport com.dss26.cards.lifecycle.card.Card\n",
           "import com.dss26.cards.events.CardFormFactor\nimport com.dss26.cards.events.ReplacementReason\n"
           "import com.dss26.cards.lifecycle.card.Card\n"),
         S(CLC_API, "    data class ActivateRequest(val channel: ActivationChannel)\n",
           final(CLC, CLC_API, "    data class ActivateRequest", "val expiryYyyymm: String)\n")),
         S(CLC_API, "        cards.block(cardToken, req.reason, req.initiator)\n}\n",
           final(CLC, CLC_API, "        cards.block(cardToken, req.reason, req.initiator)\n", "req.expiryYyyymm)\n}\n")),
     )),
    ("2024-06-10 15:05", "mateo.rossi",
     "feat(risk): block cards on risk.limit.breached.v1\n\n"
     "Risk Platform's limit engine publishes breaches; until now the contact\n"
     "centre blocked by hand from the alert email. Consumer group\n"
     "card-lifecycle-svc, starting from latest: old breaches must not block\n"
     "cards retroactively.\n\n"
     "Refs: CSERV-478, RISK-488",
     (
         F(CLC_RISK),
         *avro("src/main/avro", "risk.limit.breached.v1"),
         S(CLC_YML, "        use.latest.version: true\n",
           final(CLC, CLC_YML, "        use.latest.version: true\n", "      ack-mode: record\n")),
         Write("catalog-info.yaml", _clc_catalog(full=True)),
     )),
    ("2024-09-16 10:20", "chloe.dubois",
     "fix(risk): auto-block only on exposure and restricted-MCC breaches\n\n"
     "Blocking on velocity breaches froze 1,900 legitimate cards on the first\n"
     "Saturday of the sales. Velocity breaches go to cardholder alerts only;\n"
     "EXPOSURE and MCC_RESTRICTED still block.\n\n"
     "Refs: CSERV-497",
     (
         S(CLC_RISK,
           "/**\n * Auto-blocks a card when the risk engine reports a limit breach.\n */\n",
           final(CLC, CLC_RISK, "/**\n * Auto-blocks", " */\n")),
         S(CLC_RISK, "        val AUTO_BLOCK = LimitType.values().toSet()\n",
           "        val AUTO_BLOCK = setOf(LimitType.EXPOSURE, LimitType.MCC_RESTRICTED)\n"),
     )),
    ("2025-01-20 09:30", "mateo.rossi",
     "chore: Kotlin 2.0, Spring Boot 3.4, Confluent 7.8\n\n"
     "kotlinOptions-style task configuration is deprecated in Kotlin 2.0;\n"
     "compiler flags move to the kotlin extension.",
     (
         S(CLC_GRADLE, _CLC_PLUGINS.format(boot="3.2.3", depmgmt="1.1.4", kotlin="1.9.22"),
           _CLC_PLUGINS.format(boot="3.4.1", depmgmt="1.1.6", kotlin="2.0.21")),
         S(CLC_GRADLE, "import org.jetbrains.kotlin.gradle.tasks.KotlinCompile\n\nplugins {", "plugins {"),
         S(CLC_GRADLE,
           'tasks.withType<KotlinCompile> {\n    compilerOptions {\n        freeCompilerArgs.addAll("-Xjsr305=strict")\n    }\n}\n',
           'kotlin {\n    compilerOptions {\n        freeCompilerArgs.addAll("-Xjsr305=strict")\n    }\n}\n'),
         S(CLC_GRADLE, 'implementation("org.apache.avro:avro:1.11.3")', 'implementation("org.apache.avro:avro:1.11.4")'),
         S(CLC_GRADLE, 'implementation("io.confluent:kafka-avro-serializer:7.6.0")',
           'implementation("io.confluent:kafka-avro-serializer:7.8.0")'),
     )),
    ("2025-03-24 14:50", "mateo.rossi",
     "feat: virtual and tokenised cards start ACTIVE\n\n"
     "Virtual cards had to be activated in the app before first use, which\n"
     "made no sense for a card the customer just created in the app. Plastic\n"
     "still waits for activation.\n\n"
     "Refs: CSERV-516, DIG-655",
     (
         S(CLC_SM,
           "    /** Every card starts ISSUED and needs an activation. */\n"
           "    fun initialState(formFactor: CardFormFactor): CardState = CardState.ISSUED\n",
           final(CLC, CLC_SM, "    /** Virtual and tokenised", "else CardState.ACTIVE\n")),
         S(CLC_TEST,
           "    fun `every card starts issued`() {\n"
           "        assertEquals(CardState.ISSUED, CardStateMachine.initialState(CardFormFactor.PHYSICAL))\n"
           "        assertEquals(CardState.ISSUED, CardStateMachine.initialState(CardFormFactor.VIRTUAL))\n",
           final(CLC, CLC_TEST, "    fun `plastic cards wait", "initialState(CardFormFactor.TOKENISED))\n")),
     )),
    ("2025-11-17 14:10", "chloe.dubois",
     "feat(api): GET /v1/cards/{cardToken}\n\n"
     "fraud-case-management resolves the customer behind a card from here now\n"
     "that the CMS lookup is being retired (RISK-611). Plain read, no lock.\n\n"
     "Refs: CSERV-561",
     (
         S(CLC_API, "import jakarta.validation.constraints.Pattern\nimport org.springframework.web.bind.annotation.PathVariable",
           "import jakarta.validation.constraints.Pattern\nimport org.springframework.http.ResponseEntity\n"
           "import org.springframework.web.bind.annotation.GetMapping\n"
           "import org.springframework.web.bind.annotation.PathVariable"),
         S(CLC_API, "    @PostMapping\n    fun issue(",
           final(CLC, CLC_API, '    @GetMapping("/{cardToken}")', "    @PostMapping\n    fun issue(")),
         S(CLC_SVC, "    private fun load(cardToken: String): Card =",
           "    fun find(cardToken: String): Card? = cards.find(cardToken)\n\n"
           "    private fun load(cardToken: String): Card ="),
         S(CLC_REPO,
           "    fun findForUpdate(cardToken: String): Card? =\n"
           '        jdbc.sql("SELECT * FROM card WHERE card_token = :token FOR UPDATE")\n'
           '            .param("token", cardToken)\n',
           final(CLC, CLC_REPO, "    fun find(cardToken", '            .param("token", cardToken)\n')),
     )),
    ("2026-03-30 10:35", "mateo.rossi",
     "docs(readme): state machine, outbox, auto-block rules and runbooks",
     (F("README.md"),)),
)

CLC_SPEC = RepoSpec(
    name=CLC,
    description="Card state machine and cards.card.* events (issued, activated, blocked, replaced) via an outbox.",
    team="cards-servicing",
    domain="cards",
    tier="B",
    topics=("team-cards-servicing", "domain-cards", "kotlin", "spring-boot", "kafka"),
    history=CLC_HISTORY,
    labels=DEFAULT_LABELS + (L_KAFKA,),
)

# ===========================================================================
# Tier B - fraud-case-management (risk-platform, Python)
# ===========================================================================

FCM = "fraud-case-management"
FCM_PKG = "src/fraud_cases"
FCM_TRIAGE = f"{FCM_PKG}/triage.py"
FCM_CONFIG = f"{FCM_PKG}/config.py"
FCM_CONSUMER = f"{FCM_PKG}/consumer.py"
FCM_STORE = f"{FCM_PKG}/store.py"
FCM_API = f"{FCM_PKG}/api.py"
FCM_LOOKUP = f"{FCM_PKG}/lookup.py"
FCM_TRIAGE_TEST = "tests/test_triage.py"
FCM_FRAUD_TOPICS = ("fraud.case.opened.v1", "fraud.case.resolved.v1")


def _fcm_catalog(*, resolved: bool) -> str:
    return catalog_info(
        FCM,
        title="Fraud case management",
        description="Opens and tracks fraud investigation cases from fraud scores and cardholder reports.",
        owner="risk-platform", system="fraud-risk",
        tags=("python", "kafka", "fastapi", "tier-2"),
        dashboard=dd("m5q-7tc-w9a", FCM),
        consumes=("fraud.score.computed.v1",),
        produces=FCM_FRAUD_TOPICS if resolved else ("fraud.case.opened.v1",),
        groups=(FCM,),
        depends_on=("resource:fraud-cases-db",),
    )


FCM_README_2022 = """\
# fraud-case-management

Opens fraud investigation cases from real-time fraud scores. Consumes
`fraud.score.computed.v1` as consumer group `fraud-case-management`; every
REVIEW or DECLINE becomes a case in the analysts' queue and an event on
`fraud.case.opened.v1`.

Producer of the scores: fraud-scoring (Cards Platform).

## Running

```bash
pip install -e '.[dev]'
pytest -q
fraud-cases-consumer
```

## Owners

Risk Platform, `#risk-platform`.
"""

FCM_TRIAGE_2022 = '''\
"""Decide whether a fraud score deserves a human, and how urgently."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TriageResult:
    open_case: bool
    priority: str | None = None
    trigger: str = "MODEL_SCORE"


def triage(score: float, decision: str) -> TriageResult:
    if decision == "DECLINE":
        return TriageResult(True, "P2")
    if decision == "REVIEW":
        return TriageResult(True, "P3")
    return TriageResult(False)
'''

FCM_TRIAGE_2022_RULES = '''\
"""Decide whether a fraud score deserves a human, and how urgently.

Pure functions only: this is the part analysts argue about, so it is the part
with the tests.
"""

from __future__ import annotations

from dataclasses import dataclass

# Rules from the decisioning engine that always merit a faster look.
HIGH_RISK_RULES = frozenset({"ACCOUNT_TAKEOVER", "CARD_TESTING", "MULE_PATTERN", "SIM_SWAP_RECENT"})


@dataclass(frozen=True)
class TriageResult:
    open_case: bool
    priority: str | None = None
    trigger: str = "MODEL_SCORE"


def triage(score: float, decision: str, rule_matches: list[str]) -> TriageResult:
    high_risk = bool(HIGH_RISK_RULES.intersection(rule_matches))
    if decision == "DECLINE":
        return TriageResult(True, "P1" if score >= 0.9 or high_risk else "P2")
    if decision == "REVIEW":
        return TriageResult(True, "P2" if high_risk else "P3")
    return TriageResult(False)
'''

FCM_TRIAGE_TEST_2022 = '''\
from fraud_cases.triage import TriageResult, triage


def test_decline_opens_a_p2():
    assert triage(0.85, "DECLINE") == TriageResult(True, "P2")


def test_review_opens_a_p3():
    assert triage(0.6, "REVIEW") == TriageResult(True, "P3")


def test_approve_opens_nothing():
    assert triage(0.12, "APPROVE") == TriageResult(False)
'''

FCM_TRIAGE_TEST_2022_RULES = '''\
from fraud_cases.triage import TriageResult, triage


def test_decline_with_very_high_score_is_p1():
    assert triage(0.97, "DECLINE", []) == TriageResult(True, "P1")


def test_decline_is_p2_by_default():
    assert triage(0.82, "DECLINE", []) == TriageResult(True, "P2")


def test_high_risk_rule_escalates_a_review():
    assert triage(0.6, "REVIEW", ["CARD_TESTING"]) == TriageResult(True, "P2")
    assert triage(0.6, "REVIEW", ["NEW_DEVICE"]) == TriageResult(True, "P3")


def test_approve_opens_nothing():
    assert triage(0.12, "APPROVE", []) == TriageResult(False)
'''

FCM_LOOKUP_2022 = '''\
"""Who does an authorisation belong to? Score events only carry the auth_id."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class CardOwner:
    card_token: str
    customer_id: str


class CardOwnerLookup:
    """Authorisation lookup on the card management system (CMS) gateway."""

    def __init__(self, cms_url: str, timeout: float = 2.0) -> None:
        self._http = httpx.Client(base_url=cms_url, timeout=timeout)

    def for_auth(self, auth_id: str) -> CardOwner:
        resp = self._http.get(f"/cms/v2/authorisations/{auth_id}")
        resp.raise_for_status()
        body = resp.json()
        return CardOwner(card_token=body["cardToken"], customer_id=body["customerId"])

    def close(self) -> None:
        self._http.close()
'''

_FCM_DEPS = """\
dependencies = [
    "confluent-kafka[avro,schemaregistry]=={ck}",
{api}    "psycopg[binary,pool]=={pg}",
    "httpx=={httpx}",
]
"""
FCM_DEPS_2022 = _FCM_DEPS.format(ck="1.9.2", api="", pg="3.1.4", httpx="0.23.0")
FCM_DEPS_2023 = _FCM_DEPS.format(ck="1.9.2", api='    "fastapi==0.94.0",\n    "uvicorn[standard]==0.21.0",\n',
                                 pg="3.1.4", httpx="0.23.0")
FCM_DEPS_2025 = final(FCM, "pyproject.toml", "dependencies = [", "]\n")

FCM_HISTORY = history(
    FCM,
    ("2022-10-10 10:30", "ines.duarte",
     "feat: open fraud cases from fraud.score.computed.v1\n\n"
     "Fraud analysts work from a daily export of REVIEW/DECLINE scores. This\n"
     "service opens the case the moment the score lands: consumer group\n"
     "fraud-case-management, manual commits after the case row and the\n"
     "fraud.case.opened.v1 event are written, unique on the triggering\n"
     "auth_id so a redelivery never opens a second case.\n\n"
     "Refs: RISK-342",
     (
         Write("README.md", FCM_README_2022),
         Write("catalog-info.yaml", _fcm_catalog(resolved=False)),
         Write(".github/CODEOWNERS", "* @dss26-org/risk-platform\n"),
         F(".github/workflows/ci.yml"),
         Write(".gitignore", "__pycache__/\n*.pyc\n.venv/\n.pytest_cache/\n.ruff_cache/\n*.egg-info/\n"),
         F("pyproject.toml"),
         F(f"{FCM_PKG}/__init__.py"),
         F(FCM_CONFIG),
         Write(FCM_TRIAGE, FCM_TRIAGE_2022),
         Write(FCM_LOOKUP, FCM_LOOKUP_2022),
         F(FCM_STORE),
         F(FCM_CONSUMER),
         F("migrations/001_fraud_case.sql"),
         *avro("schemas", "fraud.score.computed.v1", "fraud.case.opened.v1"),
         Write(FCM_TRIAGE_TEST, FCM_TRIAGE_TEST_2022),
     )),
    ("2022-11-21 16:15", "yusuf.demir",
     "feat(triage): priority from score and rule matches\n\n"
     "Analysts asked for account takeover, card testing, mule patterns and\n"
     "recent SIM swaps to jump the queue whatever the score. DECLINE at 0.9 or\n"
     "above is P1 too.\n\n"
     "Refs: RISK-358",
     (
         Write(FCM_TRIAGE, FCM_TRIAGE_2022_RULES),
         Write(FCM_TRIAGE_TEST, FCM_TRIAGE_TEST_2022_RULES),
         S(FCM_CONSUMER, '            decision = triage(score["score"], score["decision"])\n',
           '            decision = triage(score["score"], score["decision"], score.get("rule_matches") or [])\n'),
     )),
    ("2023-03-06 11:00", "ines.duarte",
     "feat(api): analysts resolve cases; publish fraud.case.resolved.v1\n\n"
     "The case UI calls POST /cases/{id}/resolution with the outcome, the\n"
     "actions taken and the net loss. Loss reporting to Finance reads\n"
     "fraud.case.resolved.v1 instead of the monthly spreadsheet.\n\n"
     "Refs: RISK-391",
     (
         F(FCM_API),
         *avro("schemas", "fraud.case.resolved.v1"),
         S(FCM_STORE, "import uuid\nfrom datetime import datetime, timezone\n",
           "import uuid\nfrom datetime import datetime, timezone\nfrom decimal import Decimal\n"),
         S(FCM_STORE, "        return row\n",
           final(FCM, FCM_STORE, "        return row\n", "currency, datetime.now(timezone.utc), case_id),\n            ).fetchone()\n")),
         S("pyproject.toml", FCM_DEPS_2022, FCM_DEPS_2023),
         Write("catalog-info.yaml", _fcm_catalog(resolved=True)),
     )),
    ("2024-06-17 09:45", "yusuf.demir",
     "docs: scores now come from fraud-decisioning-svc (ADR-0011)\n\n"
     "Same topic, same schema; only the producing service and its consumer\n"
     "group were renamed.",
     (S("README.md", "Producer of the scores: fraud-scoring (Cards Platform).",
        "Producer of the scores: fraud-decisioning-svc (Cards Platform), called\n"
        "fraud-scoring before ADR-0011."),)),
    ("2024-11-12 13:20", "yusuf.demir",
     "feat(triage): second look at approvals above the review threshold\n\n"
     "When the engine approves but the score is above our review threshold,\n"
     "the model and the rules disagree; analysts want those at P4. Threshold\n"
     "is FRAUD_CASES_REVIEW_THRESHOLD (default 0.5) so it can be raised when\n"
     "the queue is long.\n\n"
     "Refs: RISK-529",
     (
         F(FCM_TRIAGE),
         F(FCM_TRIAGE_TEST),
         F("tests/test_config.py"),
         S(FCM_CONFIG, '    kafka_password: str = ""\n',
           '    kafka_password: str = ""\n    review_threshold: float = 0.5\n'),
         S(FCM_CONFIG, '            kafka_password=env.get("KAFKA_PASSWORD", ""),\n',
           '            kafka_password=env.get("KAFKA_PASSWORD", ""),\n'
           '            review_threshold=float(env.get("FRAUD_CASES_REVIEW_THRESHOLD", "0.5")),\n'),
         S(FCM_CONSUMER,
           '            decision = triage(score["score"], score["decision"], score.get("rule_matches") or [])\n',
           '            decision = triage(score["score"], score["decision"], score.get("rule_matches") or [],\n'
           '                              settings.review_threshold)\n'),
     )),
    ("2025-05-19 07:58", "platform-bot",
     "chore(deps): bump the pip group with 5 updates\n\n"
     "confluent-kafka 1.9.2 -> 2.10.0, fastapi 0.94.0 -> 0.115.6,\n"
     "uvicorn 0.21.0 -> 0.32.1, psycopg 3.1.4 -> 3.2.3, httpx 0.23.0 -> 0.28.1.",
     (S("pyproject.toml", FCM_DEPS_2023, FCM_DEPS_2025),)),
    ("2025-11-24 10:50", "yusuf.demir",
     "feat(lookup): resolve card owners from the cards servicing APIs\n\n"
     "The CMS authorisation lookup is retired at the end of the year. The\n"
     "card behind an auth_id now comes from txn-history-builder and the\n"
     "customer from card-lifecycle-svc (CSERV-560, CSERV-561).\n\n"
     "Refs: RISK-611",
     (
         F(FCM_LOOKUP),
         S(FCM_CONFIG, '    cms_url: str = "http://cms-gateway.cards-servicing.svc:8080"\n',
           '    txn_history_url: str = "http://txn-history-builder.cards-servicing.svc:8080"\n'
           '    card_lifecycle_url: str = "http://card-lifecycle-svc.cards-servicing.svc:8080"\n'),
         S(FCM_CONFIG, '            cms_url=env.get("CMS_URL", cls.cms_url),\n',
           '            txn_history_url=env.get("TXN_HISTORY_URL", cls.txn_history_url),\n'
           '            card_lifecycle_url=env.get("CARD_LIFECYCLE_URL", cls.card_lifecycle_url),\n'),
         S(FCM_CONSUMER, "    owners = CardOwnerLookup(settings.cms_url)\n",
           "    owners = CardOwnerLookup(settings.txn_history_url, settings.card_lifecycle_url)\n"),
     )),
    ("2026-02-16 15:25", "ines.duarte",
     "feat(api): cases for cardholder-reported fraud\n\n"
     "The contact centre raised these by email. POST /cases opens one with\n"
     "trigger CARDHOLDER_REPORT (no triggering auth) and publishes it like\n"
     "any other case.\n\n"
     "Refs: RISK-655",
     (
         S(FCM_API, "from fraud_cases.config import CASE_RESOLVED_TOPIC, Settings",
           "from fraud_cases.config import CASE_OPENED_TOPIC, CASE_RESOLVED_TOPIC, Settings"),
         S(FCM_API,
           'resolved_serializer = AvroSerializer(registry, open("schemas/fraud.case.resolved.v1.avsc").read(),\n'
           "                                     conf=_serializer_conf)\n",
           final(FCM, FCM_API, "resolved_serializer = ", "                                   conf=_serializer_conf)\n")),
         S(FCM_API, "    currency: str = Field(min_length=3, max_length=3)\n\n\n@app.post",
           final(FCM, FCM_API, "    currency: str = Field(min_length=3, max_length=3)\n", "@app.post")),
         S(FCM_API, '    return {"case_id": case_id, "status": "RESOLVED"}\n',
           final(FCM, FCM_API, '    return {"case_id": case_id, "status": "RESOLVED"}\n', 'return {"case_id": case["case_id"]}\n')),
     )),
    ("2026-08-03 11:30", "yusuf.demir",
     "chore: Python 3.12, ruff in CI, README refresh",
     (
         S("pyproject.toml", 'version = "1.0.0"', 'version = "3.4.0"'),
         S("pyproject.toml", 'requires-python = ">=3.10"', 'requires-python = ">=3.12"'),
         S("pyproject.toml", 'dev = ["pytest==7.2.0"]', 'dev = ["pytest==8.3.4", "ruff==0.8.4"]'),
         S("pyproject.toml", 'testpaths = ["tests"]\n',
           final(FCM, "pyproject.toml", 'testpaths = ["tests"]\n', 'target-version = "py312"\n')),
         S(".github/workflows/ci.yml", 'python-version: "3.10"', 'python-version: "3.12"'),
         S(".github/workflows/ci.yml", "      - name: Test\n",
           "      - name: Lint\n        run: ruff check src tests\n      - name: Test\n"),
         F("README.md"),
     )),
)

FCM_SPEC = RepoSpec(
    name=FCM,
    description="Fraud investigation cases from fraud.score.computed.v1 and cardholder reports.",
    team="risk-platform",
    domain="fraud",
    tier="B",
    topics=("team-risk-platform", "domain-fraud", "python", "kafka", "fastapi"),
    history=FCM_HISTORY,
    labels=DEFAULT_LABELS + (L_KAFKA,),
)

# ===========================================================================
# Tier C - aml-transaction-screening (compliance-platform, Scala)
# ===========================================================================

AML = "aml-transaction-screening"
AML_PKG = "src/main/scala/com/dss26/aml/screening"
AML_RULES = f"{AML_PKG}/rules/Rules.scala"
AML_SPEC_TEST = "src/test/scala/com/dss26/aml/screening/rules/RulesSpec.scala"
AML_MAIN = f"{AML_PKG}/Main.scala"
AML_CONF = "src/main/resources/application.conf"
AML_DOCS = "docs/typologies.md"
AML_CI = ".github/workflows/ci.yml"
AML_TOPICS_IN = ("cards.clearing.received.v1", "cards.clearing.matched.v1", "cards.card.issued.v1")
AML_TOPICS_OUT = ("aml.transaction.screened.v1", "aml.alert.raised.v1")


def _aml_catalog(*, pagerduty: bool) -> str:
    return catalog_info(
        AML,
        title="AML transaction screening",
        description="Real-time AML screening of cleared card transactions; alerts to the FIU.",
        owner="compliance-platform", system="financial-crime-compliance",
        tags=("scala", "kafka-streams", "kafka", "aml", "tier-1"),
        pagerduty="PSVC6RT" if pagerduty else None,
        opsgenie=None if pagerduty else "Compliance Platform",
        dashboard=dd("c9w-4ry-t2n", AML),
        consumes=AML_TOPICS_IN, produces=AML_TOPICS_OUT, groups=(AML,),
    )


AML_BUILD_2021 = """\
ThisBuild / scalaVersion := "2.13.5"
ThisBuild / organization := "com.dss26.aml"

lazy val root = (project in file("."))
  .settings(
    name := "aml-transaction-screening",
    libraryDependencies ++= Seq(
      "com.typesafe" % "config" % "1.4.1",
      "org.scalatest" %% "scalatest" % "3.2.5" % Test
    ),
    scalacOptions ++= Seq("-deprecation", "-feature", "-Xfatal-warnings")
  )
"""

AML_BUILD_2024 = (FILES_ROOT / AML / "build.sbt").read_text() \
    .replace('"2.13.15"', '"2.13.14"').replace('"3.8.1"', '"3.7.1"').replace('"7.8.0"', '"7.6.1"') \
    .replace('"1.5.12"', '"1.5.6"').replace('"3.2.19"', '"3.2.18"')

AML_RULES_2021 = """\
package com.dss26.aml.screening.rules

import com.dss26.aml.screening.model._

import java.time.Instant
import java.util.UUID

final case class RulesConfig(
    largeValueEur: BigDecimal,
    roundAmountMinEur: BigDecimal,
    highRiskMerchants: Set[String]
)

/**
 * Transaction-level AML rules. Typologies and their regulatory references are
 * in docs/typologies.md; every rule name here appears there.
 */
final class Rules(config: RulesConfig) {

  def screen(tx: ClearedTransaction, now: Instant = Instant.now()): ScreeningResult = {
    val eur = tx.amount
    val hits = List(
      Option.when(eur >= config.largeValueEur)(RuleHit("LARGE_VALUE", Some("LARGE_VALUE"))),
      Option.when(eur >= config.roundAmountMinEur && isRound(eur))(RuleHit("ROUND_AMOUNT", None)),
      Option.when(config.highRiskMerchants.contains(tx.merchantId))(
        RuleHit("HIGH_RISK_MERCHANT", Some("HIGH_RISK_COUNTERPARTY"))
      )
    ).flatten

    val outcome =
      if (hits.exists(_.typology.isDefined)) Outcome.Alerted
      else if (hits.nonEmpty) Outcome.Flagged
      else Outcome.Clear

    ScreeningResult(UUID.randomUUID().toString, tx, outcome, hits, now)
  }

  private def isRound(eur: BigDecimal): Boolean = eur.remainder(BigDecimal(1000)) == 0
}
"""

AML_RULES_2023 = AML_RULES_2021.replace(
    "    roundAmountMinEur: BigDecimal,\n    highRiskMerchants: Set[String]\n",
    "    roundAmountMinEur: BigDecimal,\n    structuringBandLowEur: BigDecimal,\n"
    "    structuringBandHighEur: BigDecimal,\n    structuringCount24h: Long,\n    highRiskMerchants: Set[String]\n",
).replace(
    "  private def isRound",
    "  /** Just under the large-value threshold: the band structuring hides in. */\n"
    "  def inStructuringBand(tx: ClearedTransaction): Boolean =\n"
    "    tx.amount >= config.structuringBandLowEur && tx.amount < config.structuringBandHighEur\n\n"
    "  def isStructuring(countIn24h: Long): Boolean = countIn24h >= config.structuringCount24h\n\n"
    "  private def isRound",
)

AML_SPEC_2021 = """\
package com.dss26.aml.screening.rules

import com.dss26.aml.screening.model._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

import java.time.Instant

class RulesSpec extends AnyFlatSpec with Matchers {

  private val rules = new Rules(RulesConfig(BigDecimal(10000), BigDecimal(5000), Set("MRC-0099120")))

  private def tx(amount: BigDecimal, merchant: String = "MRC-0004410") =
    ClearedTransaction("clr-1", "auth-1", "tok_1f2e3d", merchant, amount, "EUR", Some("CUST-77120"),
      Instant.parse("2021-02-01T10:00:00Z"))

  "screen" should "clear an ordinary purchase" in {
    rules.screen(tx(BigDecimal("84.20"))).outcome shouldBe Outcome.Clear
  }

  it should "alert on a large value" in {
    rules.screen(tx(BigDecimal("12000.00"))).rulesFired should contain("LARGE_VALUE")
  }

  it should "only flag a round amount below the large-value threshold" in {
    val result = rules.screen(tx(BigDecimal("6000.00")))
    result.outcome shouldBe Outcome.Flagged
    result.typology shouldBe None
  }

  it should "alert on a high-risk merchant whatever the amount" in {
    rules.screen(tx(BigDecimal("12.00"), merchant = "MRC-0099120")).typology shouldBe Some("HIGH_RISK_COUNTERPARTY")
  }
}
"""

AML_SPEC_2023 = AML_SPEC_2021.replace(
    '  private val rules = new Rules(RulesConfig(BigDecimal(10000), BigDecimal(5000), Set("MRC-0099120")))\n',
    "  private val rules = new Rules(\n"
    "    RulesConfig(BigDecimal(10000), BigDecimal(5000), BigDecimal(9000), BigDecimal(10000), 3, Set(\"MRC-0099120\"))\n"
    "  )\n",
).replace(
    '    rules.screen(tx(BigDecimal("12.00"), merchant = "MRC-0099120")).typology shouldBe Some("HIGH_RISK_COUNTERPARTY")\n  }\n}\n',
    '    rules.screen(tx(BigDecimal("12.00"), merchant = "MRC-0099120")).typology shouldBe Some("HIGH_RISK_COUNTERPARTY")\n  }\n\n'
    '  "structuring" should "use the band just under the threshold" in {\n'
    '    rules.inStructuringBand(tx(BigDecimal("9500.00"))) shouldBe true\n'
    '    rules.inStructuringBand(tx(BigDecimal("10000.00"))) shouldBe false\n'
    "    rules.isStructuring(3) shouldBe true\n  }\n}\n",
)

AML_README_2021 = """\
# aml-transaction-screening

Anti-money-laundering typology rules for card transactions, as a Scala
library. The nightly transaction monitoring batch calls it over the day's
cleared card transactions; alerts go to the Financial Intelligence Unit's
case queue.

Rules and thresholds: docs/typologies.md (owned with the MLRO's office).

## Build

```bash
sbt test
```

## Owners

Compliance Platform, `#compliance-platform`.
"""

AML_CI_2021 = """\
name: ci

on:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-java@v2
        with:
          distribution: adopt
          java-version: "11"
      - name: Format check
        run: sbt scalafmtCheckAll
      - name: Test
        run: sbt test
"""

AML_HISTORY = history(
    AML,
    ("2021-02-15 10:05", "hannah.berg",
     "feat: AML typology rules for card transactions\n\n"
     "Ports the card rules out of the 2020 monitoring spreadsheet into code\n"
     "the nightly batch can call: large value, round amounts, high-risk\n"
     "merchants. Thresholds are configuration, signed off by the MLRO.\n\n"
     "Refs: CMP-702",
     (
         Write("README.md", AML_README_2021),
         Write(".github/CODEOWNERS", "*                @dss26-org/compliance-platform\n/docs/           @dss26-org/compliance-platform @claire.martin\n"),
         Write(AML_CI, AML_CI_2021),
         Write(".gitignore", "target/\nproject/target/\n.bsp/\n.idea/\n.metals/\n"),
         Write("build.sbt", AML_BUILD_2021),
         Write("project/build.properties", "sbt.version=1.4.7\n"),
         Write("project/plugins.sbt", 'addSbtPlugin("org.scalameta" % "sbt-scalafmt" % "2.4.2")\n'),
         Write(".scalafmt.conf", "version = 2.7.5\nmaxColumn = 110\nalign.preset = more\n"),
         F(f"{AML_PKG}/model/Model.scala"),
         Write(AML_RULES, AML_RULES_2021),
         Write(AML_SPEC_TEST, AML_SPEC_2021),
     )),
    ("2021-03-08 14:20", "claire.martin",
     "docs: typology catalogue with the regulatory references\n\n"
     "For the internal audit of the transaction monitoring controls: which\n"
     "rule covers which typology, and on what basis.",
     (F(AML_DOCS),)),
    ("2023-04-24 11:35", "kwame.mensah",
     "feat(rules): structuring across 24 hours\n\n"
     "Several transactions just under the large-value threshold for one\n"
     "customer in a day. The rule only decides the band and the count; the\n"
     "counting itself happens in the batch over the customer's day.\n\n"
     "Refs: CMP-881",
     (
         Write(AML_RULES, AML_RULES_2023),
         Write(AML_SPEC_TEST, AML_SPEC_2023),
         S(AML_DOCS, "| `HIGH_RISK_MERCHANT` | HIGH_RISK_COUNTERPARTY | Merchant on the FIU's high-risk merchant list | Internal risk assessment |\n",
           "| `HIGH_RISK_MERCHANT` | HIGH_RISK_COUNTERPARTY | Merchant on the FIU's high-risk merchant list | Internal risk assessment |\n"
           "| structuring window | STRUCTURING | Three or more cleared transactions between EUR 9,000 and 10,000 for one customer within 24 hours | EU AMLD, linked transactions |\n"),
     )),
    ("2024-07-08 09:50", "hannah.berg",
     "feat: screen cleared card transactions in real time\n\n"
     "Replaces the nightly batch with a Kafka Streams application\n"
     "(application.id aml-transaction-screening): presentment joined with its\n"
     "match on clearing_id, card owner from cards.card.issued.v1 as a global\n"
     "table, rules applied per transaction, structuring counted in a 24h\n"
     "window per customer. Every screening goes to\n"
     "aml.transaction.screened.v1; alerts to aml.alert.raised.v1.\n\n"
     "Unreadable records stop the application (LogAndFailExceptionHandler):\n"
     "a gap in screening is a regulatory breach, a stopped screener is an\n"
     "incident.\n\n"
     "Refs: CMP-1044",
     (
         Write("build.sbt", AML_BUILD_2024),
         Write("project/build.properties", "sbt.version=1.10.0\n"),
         Write("project/plugins.sbt",
               'addSbtPlugin("com.eed3si9n" % "sbt-assembly" % "2.2.0")\naddSbtPlugin("org.scalameta" % "sbt-scalafmt" % "2.5.2")\n'),
         F(f"{AML_PKG}/codec/AvroCodecs.scala"),
         F(f"{AML_PKG}/ScreeningTopology.scala"),
         F(AML_MAIN),
         F(AML_CONF),
         *avro("src/main/resources/avro", *AML_TOPICS_OUT),
         Write("catalog-info.yaml", _aml_catalog(pagerduty=False)),
         S(AML_CI, "      - uses: actions/checkout@v2\n      - uses: actions/setup-java@v2\n        with:\n"
                   "          distribution: adopt\n          java-version: \"11\"\n",
           "      - uses: actions/checkout@v4\n      - uses: actions/setup-java@v4\n        with:\n"
           "          distribution: temurin\n          java-version: \"21\"\n          cache: sbt\n"),
     )),
    ("2024-09-16 15:10", "hannah.berg",
     "docs(readme): architecture and the screening-stopped runbook\n\n"
     "Written after INC-2024-09-12-003, when the clearing feed changed shape\n"
     "and screening stopped as designed. The runbook says what the FIU needs\n"
     "to hear and why we never skip offsets.",
     (F("README.md"),)),
    ("2025-01-13 10:25", "kwame.mensah",
     "ci: install sbt explicitly\n\n"
     "ubuntu-latest is 24.04 now and no longer ships sbt.",
     (S(AML_CI, "          cache: sbt\n", "          cache: sbt\n      - uses: sbt/setup-sbt@v1\n"),)),
    ("2025-03-17 14:00", "kwame.mensah",
     "feat(rules): EUR equivalents for non-euro transactions\n\n"
     "Thresholds are set in euro but about 4% of cleared volume is USD, GBP,\n"
     "CHF, SEK or PLN, which was compared at face value. Amounts are now\n"
     "converted at the ECB reference rates (refreshed daily by the deploy job);\n"
     "an unknown currency is still screened at face value.\n\n"
     "Refs: CMP-1188",
     (
         F(f"{AML_PKG}/rules/FxRates.scala"),
         F(AML_RULES),
         F(AML_SPEC_TEST),
         S(AML_MAIN, "import com.dss26.aml.screening.rules.{Rules, RulesConfig}",
           "import com.dss26.aml.screening.rules.{FxRates, Rules, RulesConfig}"),
         S(AML_MAIN, '    val rules    = new Rules(rulesConfig(conf.getConfig("rules")))\n',
           '    val rules    = new Rules(rulesConfig(conf.getConfig("rules")), fxRates(conf.getConfig("fx")))\n'),
         S(AML_MAIN, "      highRiskMerchants = c.getStringList(\"high-risk-merchants\").asScala.toSet\n    )\n}\n",
           final(AML, AML_MAIN, '      highRiskMerchants = c.getStringList("high-risk-merchants").asScala.toSet\n', "toMap)\n}\n")),
         S(AML_CONF, "    high-risk-merchants = ${?AML_HIGH_RISK_MERCHANTS}\n  }\n}\n",
           final(AML, AML_CONF, "    high-risk-merchants = ${?AML_HIGH_RISK_MERCHANTS}\n", "    PLN = 4.2780\n  }\n}\n")),
         S(AML_DOCS, "| One cleared transaction of EUR 10,000 or more |",
           "| One cleared transaction of EUR 10,000 or more (EUR equivalent at the ECB reference rate) |"),
     )),
    ("2025-04-14 09:15", "kwame.mensah",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired. Service PSVC6RT, escalation policy\n"
     "\"Compliance Platform - Primary\".",
     (
         Write("catalog-info.yaml", _aml_catalog(pagerduty=True)),
         S("README.md", 'Tier 1. Paging through Opsgenie (team "Compliance Platform"). Pages on: any',
           'Tier 1. PagerDuty service `PSVC6RT`, escalation policy "Compliance Platform -\nPrimary". Pages on: any'),
     )),
    ("2026-01-26 11:00", "claire.martin",
     "docs: note the AML Regulation timeline\n\n"
     "AMLR (EU) 2024/1624 applies from 10 July 2027. Thresholds do not\n"
     "change; the article-by-article mapping is tracked in CMP-1310.",
     (S(AML_DOCS, "customer relationship (AMLD article 40). The record of evidence is the FIU's\ncase management system, not this service.\n",
        final(AML, AML_DOCS, "customer relationship (AMLD article 40).", "Thresholds above are unchanged by it.\n")),)),
    ("2026-06-08 07:45", "platform-bot",
     "chore(deps): update Kafka Streams, Confluent serde, Scala, logback, scalatest and sbt plugins",
     (F("build.sbt"), F("project/build.properties"), F("project/plugins.sbt"), F(".scalafmt.conf"))),
)

AML_SPEC = RepoSpec(
    name=AML,
    description="Real-time AML screening of cleared card transactions (Kafka Streams, Scala).",
    team="compliance-platform",
    domain="aml",
    tier="C",
    topics=("team-compliance-platform", "domain-aml", "scala", "kafka-streams", "kafka", "tier-1"),
    history=AML_HISTORY,
    labels=DEFAULT_LABELS + (L_COMPLIANCE, L_KAFKA),
)

# ===========================================================================
# Tier C - sanctions-screening-svc (compliance-platform, Go)
# ===========================================================================

SAN = "sanctions-screening-svc"
SAN_MAIN = "cmd/sanctions-screening/main.go"
SAN_HANDLER = "internal/api/handler.go"
SAN_LISTS = "internal/lists/lists.go"
SAN_PARSERS = "internal/lists/parsers.go"


def _san_catalog(*, pagerduty: bool, rescreen: bool) -> str:
    return catalog_info(
        SAN,
        title="Sanctions screening",
        description="Screens names against OFAC, UN, EU and UK sanctions lists; API for onboarding and payments.",
        owner="compliance-platform", system="financial-crime-compliance",
        tags=("go", "kafka", "sanctions", "tier-1"),
        pagerduty="PSVC9HM" if pagerduty else None,
        opsgenie=None if pagerduty else "Compliance Platform",
        dashboard=dd("s3n-8jd-k5v", "sanctions-screening"),
        consumes=("customer.profile.updated.v1",) if rescreen else (),
        produces=("sanctions.screening.completed.v1",),
        groups=(SAN,) if rescreen else (),
    )


SAN_GOMOD_2024 = """\
module github.com/dss26-org/sanctions-screening-svc

go 1.22

require golang.org/x/text v0.14.0
"""

SAN_GOMOD_2024_EVENTS = """\
module github.com/dss26-org/sanctions-screening-svc

go 1.22

require (
	github.com/hamba/avro/v2 v2.20.1
	github.com/twmb/franz-go v1.16.1
	github.com/twmb/franz-go/pkg/sr v1.0.0
	golang.org/x/text v0.14.0
)
"""

SAN_README_2024 = """\
# sanctions-screening-svc

Sanctions screening for DSS26 Bank: OFAC SDN, UN consolidated, EU FSF and the
OFSI consolidated list (UK). Replaces the screening appliance. Synchronous
API, `POST /v1/screenings`, for onboarding (kyc-onboarding-svc) and
cross-border payments (payments-hub).

Lists are reloaded every 30 minutes; a failed reload keeps the previous
complete set. Names are normalised and scored with Jaro-Winkler; 0.88 and
above goes to an analyst.

## Running

```bash
go test ./...
go run ./cmd/sanctions-screening
```

## Owners

Compliance Platform, `#compliance-platform`.
"""

SAN_PARSE_UK_OFSI = """\
// parseUK reads the OFSI consolidated list (2022 format): one
// FinancialSanctionsTarget per name, grouped by GroupID.
func parseUK(r io.Reader) ([]Entry, error) {
	var doc struct {
		Targets []struct {
			GroupID   string `xml:"GroupID"`
			Name6     string `xml:"Name6"`
			AliasType string `xml:"AliasType"`
		} `xml:"FinancialSanctionsTarget"`
	}
	if err := xml.NewDecoder(r).Decode(&doc); err != nil {
		return nil, err
	}
	byGroup := map[string]*Entry{}
	var order []string
	for _, t := range doc.Targets {
		e, ok := byGroup[t.GroupID]
		if !ok {
			e = &Entry{ID: "UK-" + t.GroupID, List: UKSanctions}
			byGroup[t.GroupID] = e
			order = append(order, t.GroupID)
		}
		if t.AliasType == "Primary name" && e.Name == "" {
			e.Name = t.Name6
		} else if t.Name6 != "" {
			e.Aliases = append(e.Aliases, t.Name6)
		}
	}
	out := make([]Entry, 0, len(order))
	for _, id := range order {
		out = append(out, *byGroup[id])
	}
	return out, nil
}
"""

SAN_IMPORTS_2024 = """\
import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/dss26-org/sanctions-screening-svc/internal/api"
	"github.com/dss26-org/sanctions-screening-svc/internal/lists"
	"github.com/dss26-org/sanctions-screening-svc/internal/match"
)
"""

SAN_HANDLER_LITERAL_2024 = """\
	h := &api.Handler{
		Matcher: matcher.Load,
		Lists:   []string{string(lists.OFACSDN), string(lists.UNConsolidated), string(lists.EU), string(lists.UKSanctions)},
		NewID:   newID,
	}
"""

SAN_HISTORY = history(
    SAN,
    ("2024-03-04 10:40", "hannah.berg",
     "feat: sanctions screening service\n\n"
     "Replaces the screening appliance, whose support contract ends in June.\n"
     "Loads OFAC SDN, UN, EU FSF and the OFSI consolidated list every 30\n"
     "minutes (keeps the previous complete set if any source fails), folds\n"
     "names and scores them with Jaro-Winkler. The 0.88 threshold comes from\n"
     "the appliance calibration against the OFAC test set.\n\n"
     "Refs: CMP-1021",
     (
         Write("README.md", SAN_README_2024),
         Write("catalog-info.yaml", _san_catalog(pagerduty=False, rescreen=False)),
         Write(".github/CODEOWNERS", "* @dss26-org/compliance-platform\n"),
         F(".github/workflows/ci.yml"),
         Write(".gitignore", "/bin/\n*.test\ncoverage.out\n"),
         Write("go.mod", SAN_GOMOD_2024),
         F(SAN_MAIN),
         F(SAN_LISTS),
         F(SAN_PARSERS),
         F("internal/match/normalize.go"),
         F("internal/match/jarowinkler.go"),
         F("internal/match/matcher.go"),
         F("internal/match/matcher_test.go"),
         F(SAN_HANDLER),
     )),
    ("2024-04-15 14:20", "kwame.mensah",
     "feat(events): publish sanctions.screening.completed.v1\n\n"
     "Every screening outcome goes on Kafka, keyed by customer, so case\n"
     "management and the audit trail stop scraping the API logs. The subject\n"
     "is registered by CI; the service only looks up the latest version. A\n"
     "failed publish never changes the answer the caller gets.\n\n"
     "Refs: CMP-1037",
     (
         F("internal/events/publisher.go"),
         *avro("internal/events/schemas", "sanctions.screening.completed.v1"),
         Write("go.mod", SAN_GOMOD_2024_EVENTS),
         S(SAN_HANDLER, '\t"encoding/json"\n\t"net/http"\n\n',
           '\t"encoding/json"\n\t"log/slog"\n\t"net/http"\n\t"time"\n\n'),
         S(SAN_HANDLER, "type Handler struct {",
           final(SAN, SAN_HANDLER, "// Recorder publishes the outcome", "type Handler struct {")),
         S(SAN_HANDLER, "\tMatcher func() *match.Matcher\n\tLists   []string\n\tNewID   func() string\n",
           "\tMatcher  func() *match.Matcher\n\tLists    []string\n\tRecorder Recorder\n\tNewID    func() string\n"),
         S(SAN_HANDLER, "\t\tresp.MatchScore = hits[0].Score\n\t}\n\tw.Header()",
           final(SAN, SAN_HANDLER, "\t\tresp.MatchScore = hits[0].Score\n", "\tw.Header()")),
         S(SAN_MAIN, SAN_IMPORTS_2024,
           final(SAN, SAN_MAIN, "import (\n", "internal/match\"\n)\n")),
         S(SAN_MAIN, "\t}()\n\n\th := &api.Handler{",
           "\t}()\n\n" + final(SAN, SAN_MAIN, "\tbrokers := strings.Split", "\th := &api.Handler{")),
         S(SAN_MAIN, SAN_HANDLER_LITERAL_2024,
           final(SAN, SAN_MAIN, "\th := &api.Handler{", "\t\tNewID:    newID,\n\t}\n")),
     )),
    ("2024-06-03 11:10", "kwame.mensah",
     "feat: rescreen customers when their identifying data changes\n\n"
     "Consumer group sanctions-screening-svc on customer.profile.updated.v1.\n"
     "A change to name, date of birth, nationality or address triggers a new\n"
     "screening with the current lists. Offsets are committed only after the\n"
     "batch is screened and recorded.\n\n"
     "Refs: CMP-1062",
     (
         F("internal/events/profile_consumer.go"),
         *avro("internal/events/schemas", "customer.profile.updated.v1"),
         S(SAN_MAIN, "\t\tNewID:    newID,\n\t}\n\n\tsrv := &http.Server",
           "\t\tNewID:    newID,\n\t}\n\n"
           + final(SAN, SAN_MAIN, "\tconsumer, err := kgo.NewClient(", "\t}()\n\n\tsrv := &http.Server")),
         Write("catalog-info.yaml", _san_catalog(pagerduty=False, rescreen=True)),
         F("README.md"),
     )),
    ("2024-10-21 07:52", "platform-bot",
     "chore(deps): bump github.com/twmb/franz-go from 1.16.1 to 1.18.0",
     (S("go.mod", "\tgithub.com/twmb/franz-go v1.16.1\n", "\tgithub.com/twmb/franz-go v1.18.0\n"),)),
    ("2025-03-03 16:05", "kwame.mensah",
     "chore: Go 1.24, x/text, avro and sr updates",
     (F("go.mod"),)),
    ("2025-04-14 09:20", "hannah.berg",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired. Service PSVC9HM, escalation policy\n"
     "\"Compliance Platform - Primary\".",
     (
         Write("catalog-info.yaml", _san_catalog(pagerduty=True, rescreen=True)),
         S("README.md",
           'Tier 1: payments cannot leave without a screening. Paging through Opsgenie\n(team "Compliance Platform"). Pages when any',
           'Tier 1: payments cannot leave without a screening. PagerDuty service\n`PSVC9HM`, escalation policy "Compliance Platform - Primary". Pages when any'),
     )),
    ("2026-01-19 10:15", "kwame.mensah",
     "feat(lists): UK Sanctions List replaces the OFSI consolidated list\n\n"
     "OFSI closes its consolidated list on 28 January 2026; the FCDO UK\n"
     "Sanctions List is the single UK source from then. Same entries, new\n"
     "format: designations carry their names, no more grouping rows by\n"
     "GroupID. Ran both in parallel in uat for two weeks: identical hit sets.\n\n"
     "Refs: CMP-1302",
     (
         S(SAN_LISTS, '{UKSanctions, "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.xml", parseUK},',
           '{UKSanctions, "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml", parseUK},'),
         S(SAN_PARSERS, SAN_PARSE_UK_OFSI, final(SAN, SAN_PARSERS, "// parseUK reads", "\treturn out, nil\n}\n")),
         S("README.md", "Financial Sanctions Files and the OFSI consolidated list (UK). Synchronous API for",
           "Financial Sanctions Files and the UK Sanctions List. Synchronous API for"),
     )),
)

SAN_SPEC = RepoSpec(
    name=SAN,
    description="Sanctions list screening (OFAC, UN, EU, UK) for onboarding, payments and rescreening.",
    team="compliance-platform",
    domain="sanctions",
    tier="C",
    topics=("team-compliance-platform", "domain-sanctions", "go", "kafka", "tier-1"),
    history=SAN_HISTORY,
    labels=DEFAULT_LABELS + (L_COMPLIANCE,),
)

# ===========================================================================
# Tier C - kyc-onboarding-svc (compliance-platform, Kotlin)
# ===========================================================================

KYC = "kyc-onboarding-svc"
KYC_PKG = "src/main/kotlin/com/dss26/kyc/onboarding"
KYC_SVC = f"{KYC_PKG}/verification/VerificationService.kt"
KYC_RATER = f"{KYC_PKG}/verification/RiskRater.kt"
KYC_SANCTIONS = f"{KYC_PKG}/sanctions/SanctionsClient.kt"
KYC_APP = f"{KYC_PKG}/KycOnboardingApplication.kt"
KYC_YML = "src/main/resources/application.yml"
KYC_TEST = "src/test/kotlin/com/dss26/kyc/onboarding/verification/RiskRaterTest.kt"


def _kyc_catalog(*, events: bool, pagerduty: bool) -> str:
    return catalog_info(
        KYC,
        title="KYC onboarding",
        description="Identity verification, sanctions screening and risk rating for new customers.",
        owner="compliance-platform", system="financial-crime-compliance",
        tags=("kotlin", "spring-boot", "kyc", "tier-1") + (("kafka",) if events else ()),
        pagerduty="PSVC2XF" if pagerduty else None,
        opsgenie=None if pagerduty else "Compliance Platform",
        dashboard=dd("b6k-2mp-z8r", "kyc-onboarding"),
        produces=("kyc.verification.completed.v1",) if events else (),
        depends_on=("component:sanctions-screening-svc",) if pagerduty else (),
    )


_KYC_BUILD = """\
import org.jetbrains.kotlin.gradle.tasks.KotlinCompile

plugins {{
    id("org.springframework.boot") version "{boot}"
    id("io.spring.dependency-management") version "{depmgmt}"
{avro_plugin}    kotlin("jvm") version "{kotlin}"
    kotlin("plugin.spring") version "{kotlin}"
}}

group = "com.dss26.kyc"
java.sourceCompatibility = JavaVersion.VERSION_{java}

repositories {{
    mavenCentral()
{confluent_repo}}}

dependencies {{
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
{kafka_dep}    implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
    implementation("org.jetbrains.kotlin:kotlin-reflect")
{avro_deps}    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit5")
}}

tasks.withType<KotlinCompile> {{
    kotlinOptions {{
        freeCompilerArgs = listOf("-Xjsr305=strict")
        jvmTarget = "{java}"
    }}
}}

tasks.withType<Test> {{
    useJUnitPlatform()
}}
"""
KYC_BUILD_2021 = _KYC_BUILD.format(boot="2.5.3", depmgmt="1.0.11.RELEASE", avro_plugin="", kotlin="1.5.21", java=11,
                                   confluent_repo="", kafka_dep="", avro_deps="")


def _kyc_build_events(boot, depmgmt, avro_plugin, kotlin, java, avro, confluent):
    return _KYC_BUILD.format(
        boot=boot, depmgmt=depmgmt, kotlin=kotlin, java=java,
        avro_plugin=f'    id("com.github.davidmc24.gradle.plugin.avro") version "{avro_plugin}"\n',
        confluent_repo='    maven("https://packages.confluent.io/maven/")\n',
        kafka_dep='    implementation("org.springframework.kafka:spring-kafka")\n',
        avro_deps=f'    implementation("org.apache.avro:avro:{avro}")\n'
                  f'    implementation("io.confluent:kafka-avro-serializer:{confluent}")\n')


KYC_BUILD_2022 = _kyc_build_events("2.7.3", "1.0.13.RELEASE", "1.3.0", "1.6.21", 11, "1.11.0", "7.1.1")
KYC_BUILD_2023 = _kyc_build_events("3.1.4", "1.1.3", "1.8.0", "1.9.10", 17, "1.11.2", "7.4.1")

KYC_README_2021 = """\
# kyc-onboarding-svc

KYC for new DSS26 Bank customers: collects the IDV provider's report for the
applicant's identity session, screens the name against the sanctions lists
and decides PASS, FAIL or MANUAL_REVIEW.

## Running

```bash
gradle bootRun
```

## Owners

Compliance Platform, `#compliance-platform`. Paging: Opsgenie team
"Compliance Platform".
"""

KYC_HISTORY = history(
    KYC,
    ("2021-08-16 10:20", "hannah.berg",
     "feat: KYC checks for digital onboarding\n\n"
     "The app's onboarding journey hands over after the IDV session (document\n"
     "photo, selfie, liveness). We fetch the provider's report, screen the\n"
     "name on the screening appliance and decide; anything uncertain goes to\n"
     "the manual review queue. Verifications are stored with their expiry for\n"
     "the periodic review cycle.\n\n"
     "Refs: CMP-744",
     (
         Write("README.md", KYC_README_2021),
         Write("catalog-info.yaml", _kyc_catalog(events=False, pagerduty=False)),
         Write(".github/CODEOWNERS", "*        @dss26-org/compliance-platform\n"),
         F(".github/workflows/ci.yml"),
         Write(".gitignore", GITIGNORE_GRADLE),
         F("settings.gradle.kts"),
         Write("build.gradle.kts", KYC_BUILD_2021),
         F(KYC_APP),
         F(f"{KYC_PKG}/application/OnboardingController.kt"),
         F(f"{KYC_PKG}/verification/Model.kt"),
         F(f"{KYC_PKG}/verification/IdvClient.kt"),
         F(KYC_SANCTIONS),
         F(KYC_SVC),
         F(KYC_YML),
     )),
    ("2022-01-24 15:10", "hannah.berg",
     "feat: customer risk rating at onboarding\n\n"
     "Business-wide risk assessment 2021, signed off by Compliance: PEP status,\n"
     "high-risk third countries (EU list and FATF increased monitoring),\n"
     "residence outside the EEA, potential sanctions match. The rating drives\n"
     "the review cycle: 1, 3 or 5 years.\n\n"
     "Refs: CMP-790",
     (
         F(KYC_RATER),
         F(KYC_TEST),
         S(KYC_SVC, "        val rating = if (potentialMatch) RiskRating.HIGH else RiskRating.LOW\n",
           "        val rating = RiskRater.rate(applicant, potentialMatch)\n"),
     )),
    ("2022-09-19 11:45", "hannah.berg",
     "feat(events): publish kyc.verification.completed.v1\n\n"
     "customer-profile-svc opens the account from this event instead of\n"
     "polling our database. Sent after the commit, keyed by customer.\n\n"
     "Refs: CMP-842",
     (
         F(f"{KYC_PKG}/events/KycEventPublisher.kt"),
         *avro("src/main/avro", "kyc.verification.completed.v1"),
         Write("build.gradle.kts", KYC_BUILD_2022),
         S(KYC_SVC, "import com.dss26.kyc.onboarding.sanctions.SanctionsClient\n",
           "import com.dss26.kyc.onboarding.events.KycEventPublisher\nimport com.dss26.kyc.onboarding.sanctions.SanctionsClient\n"),
         S(KYC_SVC, "    private val sanctions: SanctionsClient,\n",
           "    private val sanctions: SanctionsClient,\n    private val events: KycEventPublisher,\n"),
         S(KYC_SVC, "        )\n        return result\n", "        )\n        events.verificationCompleted(result)\n        return result\n"),
         S(KYC_YML, "    password: ${KYC_DB_PASSWORD}\n",
           final(KYC, KYC_YML, "    password: ${KYC_DB_PASSWORD}\n", "        use.latest.version: true\n")),
         Write("catalog-info.yaml", _kyc_catalog(events=True, pagerduty=False)),
     )),
    ("2023-06-26 10:05", "kwame.mensah",
     "feat: open refresh tasks 30 days before a verification expires\n\n"
     "Periodic review was a quarterly spreadsheet export. A nightly job now\n"
     "opens a refresh task per expiring PASS verification; the app asks the\n"
     "customer to re-verify, and customer-profile-svc restricts the account\n"
     "if it is not done by expiry.\n\n"
     "Refs: CMP-905",
     (
         F(f"{KYC_PKG}/refresh/PeriodicRefreshJob.kt"),
         S(KYC_APP, "import org.springframework.boot.runApplication\n",
           "import org.springframework.boot.runApplication\nimport org.springframework.scheduling.annotation.EnableScheduling\n"),
         S(KYC_APP, "@SpringBootApplication\nclass", "@SpringBootApplication\n@EnableScheduling\nclass"),
     )),
    ("2023-10-09 14:30", "kwame.mensah",
     "chore: Spring Boot 3.1, Kotlin 1.9, Java 17",
     (Write("build.gradle.kts", KYC_BUILD_2023), S(".github/workflows/ci.yml", 'java-version: "11"', 'java-version: "17"'))),
    ("2024-03-11 09:55", "kwame.mensah",
     "feat(sanctions): screen through sanctions-screening-svc\n\n"
     "The screening appliance is switched off at the end of the month. Same\n"
     "decision rule: a POTENTIAL_MATCH sends the application to manual review.\n\n"
     "Refs: CMP-1024",
     (
         S(KYC_SANCTIONS, "/** Screening appliance REST API. */\n", "/** sanctions-screening-svc, POST /v1/screenings. */\n"),
         S(KYC_SANCTIONS,
           '        rest.postForObject("/api/v2/screen", ScreeningRequest(customerId, fullName, "ACCOUNT_OPEN"),',
           '        rest.postForObject("/v1/screenings", ScreeningRequest(customerId, fullName, "ACCOUNT_OPEN"),'),
         S(KYC_YML, "    base-url: ${KYC_SANCTIONS_URL}\n",
           "    base-url: ${KYC_SANCTIONS_URL:http://sanctions-screening-svc.compliance-platform.svc:8080}\n"),
     )),
    ("2024-10-07 16:15", "kwame.mensah",
     "feat(risk): strong electronic identification lowers residual risk\n\n"
     "eIDAS-notified eIDs (and in-branch identification) are now accepted as\n"
     "verification methods; Compliance agreed they lower residual risk by one\n"
     "step.\n\n"
     "Refs: CMP-1101",
     (
         S(KYC_RATER, "        if (sanctionsPotentialMatch) score += 3\n",
           final(KYC, KYC_RATER, "        if (sanctionsPotentialMatch) score += 3\n", "score -= 1\n")),
         S(KYC_TEST, "    @Test\n    fun `review cycle follows the rating`()",
           final(KYC, KYC_TEST, "    @Test\n    fun `electronic ID offsets", "    @Test\n    fun `review cycle follows the rating`()")),
     )),
    ("2025-01-20 11:00", "kwame.mensah",
     "chore: Java 21, Kotlin 2.0, Spring Boot 3.4",
     (F("build.gradle.kts"), S(".github/workflows/ci.yml", 'java-version: "17"', 'java-version: "21"'))),
    ("2025-04-14 09:25", "kwame.mensah",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired. Service PSVC2XF, escalation policy\n"
     "\"Compliance Platform - Primary\".",
     (
         Write("catalog-info.yaml", _kyc_catalog(events=True, pagerduty=True)),
         S("README.md", 'Paging: Opsgenie team\n"Compliance Platform".', "Paging: PagerDuty service `PSVC2XF`."),
     )),
    ("2026-03-02 15:40", "claire.martin",
     "docs(readme): flow, risk rating and data retention\n\n"
     "Rewritten for the 2026 internal audit of onboarding controls: what is\n"
     "checked, how the rating is derived, how long records are kept and\n"
     "where the AMLR changes things.",
     (F("README.md"),)),
)

KYC_SPEC = RepoSpec(
    name=KYC,
    description="KYC checks for digital onboarding: IDV, sanctions screening, risk rating, periodic review.",
    team="compliance-platform",
    domain="kyc",
    tier="C",
    topics=("team-compliance-platform", "domain-kyc", "kotlin", "spring-boot", "kafka", "tier-1"),
    history=KYC_HISTORY,
    labels=DEFAULT_LABELS + (L_COMPLIANCE,),
)

# ===========================================================================
# Tier C - customer-profile-svc (customer-platform, Java)
# ===========================================================================

CUS = "customer-profile-svc"
CUS_PKG = "src/main/java/com/dss26/customer/profile"
CUS_EVENTS = f"{CUS_PKG}/events/CustomerEvents.java"
CUS_PROFILE_SVC = f"{CUS_PKG}/profile/ProfileService.java"
CUS_API = f"{CUS_PKG}/api/ProfileController.java"
CUS_CONSENT = f"{CUS_PKG}/consent/ConsentService.java"
CUS_YML = "src/main/resources/application.yml"
CUS_PRODUCES = ("customer.account.opened.v1", "customer.profile.updated.v1", "customer.consent.granted.v1")
CUS_PARENT = "    <artifactId>spring-boot-starter-parent</artifactId>\n    <version>{}</version>"


def _cus_catalog(*, produces: tuple[str, ...], kyc: bool) -> str:
    return catalog_info(
        CUS,
        title="Customer profile",
        description="Customer master: profile, contact data, consents (PSD2, GDPR) and first account opening.",
        owner="customer-platform", system="customer-data",
        tags=("java", "spring-boot", "kafka", "gdpr", "tier-2"),
        dashboard=dd("f2x-9qa-h4m", "customer-profile"),
        consumes=("kyc.verification.completed.v1",) if kyc else (),
        produces=produces, groups=(CUS,) if kyc else (),
        depends_on=("component:core-banking-adapter",) if kyc else (),
    )


CUS_README_2021 = """\
# customer-profile-svc

Customer master for DSS26 Bank: name, contact data and marketing
preferences, behind `GET/PUT /v1/customers/{id}`. Replaces the customer
screens of the old CRM.

## Build

```bash
mvn -B verify
```

## Owners

Customer Platform, `#customer-platform`.
"""

CUS_API_2021 = """\
package com.dss26.customer.profile.api;

import com.dss26.customer.profile.profile.Profile;
import com.dss26.customer.profile.profile.ProfileService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/customers")
public class ProfileController {

    private final ProfileService profiles;

    public ProfileController(ProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/{customerId}")
    public ResponseEntity<Profile> get(@PathVariable String customerId) {
        return ResponseEntity.of(profiles.find(customerId));
    }

    @PutMapping("/{customerId}")
    public Profile update(@PathVariable String customerId, @RequestBody Profile profile) {
        return profiles.update(profile);
    }
}
"""

_CUS_API_FINAL = (FILES_ROOT / CUS / CUS_API).read_text()


def _without(text: str, *parts: str) -> str:
    for part in parts:
        if text.count(part) != 1:
            raise ValueError(f"{CUS}: expected one {part[:50]!r}")
        text = text.replace(part, "", 1)
    return text


# Before GDPR erasure (2023-11): no ErasureService, no DELETE endpoint.
CUS_API_2022 = _without(
    _CUS_API_FINAL,
    "import com.dss26.customer.profile.gdpr.ErasureService;\n",
    "import org.springframework.web.bind.annotation.DeleteMapping;\n",
    "    private final ErasureService erasure;\n",
    ", ErasureService erasure",
    "        this.erasure = erasure;\n",
    final(CUS, CUS_API, "\n    @DeleteMapping", "build();\n    }\n"),
)

CUS_KAFKA_DEPS = final(CUS, "pom.xml", "    <dependency>\n      <groupId>org.springframework.kafka</groupId>",
                       "      <version>${avro.version}</version>\n    </dependency>\n")
CUS_AVRO_PLUGIN = final(CUS, "pom.xml", "      <plugin>\n        <groupId>org.apache.avro</groupId>", "      </plugin>\n")
CUS_REPOS = final(CUS, "pom.xml", "  <repositories>", "  </repositories>\n\n")

CUS_HISTORY = history(
    CUS,
    ("2021-10-04 10:15", "lucas.moreau",
     "feat: customer profile service\n\n"
     "First step out of the CRM: the profile record (name, contact data,\n"
     "marketing preferences) and its API for the channels. ChangedFields\n"
     "records exactly which fields an update touched, for the audit log now\n"
     "and for events later.\n\n"
     "Refs: CUST-118",
     (
         Write("README.md", CUS_README_2021),
         Write("catalog-info.yaml", _cus_catalog(produces=(), kyc=False)),
         Write(".github/CODEOWNERS", "* @dss26-org/customer-platform\n"),
         F(".github/workflows/ci.yml"),
         Write(".gitignore", GITIGNORE_MAVEN),
         F("pom.xml"),
         F(f"{CUS_PKG}/CustomerProfileApplication.java"),
         F(f"{CUS_PKG}/profile/Profile.java"),
         F(f"{CUS_PKG}/profile/ChangedFields.java"),
         F(CUS_PROFILE_SVC),
         Write(CUS_API, CUS_API_2021),
         F(CUS_YML),
         F("src/main/resources/db/migration/V1__customer_profile.sql"),
         F("src/test/java/com/dss26/customer/profile/profile/ChangedFieldsTest.java"),
     )),
    ("2022-05-16 14:00", "lucas.moreau",
     "feat(events): publish customer.profile.updated.v1\n\n"
     "The audit log and the contact-data consumers poll the CRM extract every\n"
     "night. Every effective change now publishes the changed field names (never\n"
     "the values), who made it, and the contact-centre operator if any. Sent\n"
     "after the commit.\n\n"
     "Refs: CUST-204",
     (
         F(CUS_EVENTS),
         *avro("src/main/avro", "customer.profile.updated.v1"),
         S("pom.xml", CUS_PARENT.format("2.5.5"), CUS_PARENT.format("2.6.7")),
         S("pom.xml", "  </properties>\n\n  <dependencies>",
           "    <confluent.version>7.1.1</confluent.version>\n    <avro.version>1.11.0</avro.version>\n"
           "  </properties>\n\n" + CUS_REPOS + "  <dependencies>"),
         S("pom.xml", "    <dependency>\n      <groupId>org.flywaydb</groupId>",
           CUS_KAFKA_DEPS + "    <dependency>\n      <groupId>org.flywaydb</groupId>"),
         S("pom.xml", "    <plugins>\n      <plugin>\n        <groupId>org.springframework.boot</groupId>",
           "    <plugins>\n" + CUS_AVRO_PLUGIN + "      <plugin>\n        <groupId>org.springframework.boot</groupId>"),
         S(CUS_PROFILE_SVC, "package com.dss26.customer.profile.profile;\n\nimport org.springframework",
           "package com.dss26.customer.profile.profile;\n\nimport com.dss26.customer.profile.events.CustomerEvents;\n"
           "import org.springframework"),
         S(CUS_PROFILE_SVC,
           "    private final NamedParameterJdbcTemplate jdbc;\n\n"
           "    public ProfileService(NamedParameterJdbcTemplate jdbc) {\n        this.jdbc = jdbc;\n    }\n",
           final(CUS, CUS_PROFILE_SVC, "    private final NamedParameterJdbcTemplate jdbc;\n", "        this.events = events;\n    }\n")),
         S(CUS_PROFILE_SVC, "    public Profile update(Profile after) {",
           "    public Profile update(Profile after, String changedBy, String agentId) {"),
         S(CUS_PROFILE_SVC, "after.marketingSms()));\n        return after;",
           "after.marketingSms()));\n        events.profileUpdated(after.customerId(), changed, changedBy, agentId);\n        return after;"),
         S(CUS_API, "import org.springframework.web.bind.annotation.RequestBody;\n",
           "import org.springframework.web.bind.annotation.RequestBody;\nimport org.springframework.web.bind.annotation.RequestHeader;\n"),
         S(CUS_API,
           '    @PutMapping("/{customerId}")\n'
           "    public Profile update(@PathVariable String customerId, @RequestBody Profile profile) {\n"
           "        return profiles.update(profile);\n    }\n",
           final(CUS, CUS_API, "    /** Channels send X-Changed-By", "return profiles.update(profile, changedBy, operatorId);\n    }\n")),
         S(CUS_YML, "    password: ${CUSTOMER_DB_PASSWORD}\n",
           final(CUS, CUS_YML, "    password: ${CUSTOMER_DB_PASSWORD}\n", "        use.latest.version: true\n")),
         Write("catalog-info.yaml", _cus_catalog(produces=("customer.profile.updated.v1",), kyc=False)),
     )),
    ("2022-11-14 11:30", "lucas.moreau",
     "feat(consent): record consents and publish customer.consent.granted.v1\n\n"
     "PSD2 access for third-party providers, marketing channels and data\n"
     "sharing, each stored as an immutable grant and published as evidence\n"
     "for the PSD2 and GDPR audits. AISP consents expire after 90 days (RTS\n"
     "article 10).\n\n"
     "Refs: CUST-262",
     (
         F(CUS_CONSENT),
         F("src/main/resources/db/migration/V2__customer_consent.sql"),
         *avro("src/main/avro", "customer.consent.granted.v1"),
         S(CUS_EVENTS, "import com.dss26.customer.events.ChangedBy;\nimport com.dss26.customer.events.ProfileUpdated;",
           "import com.dss26.customer.events.ChangedBy;\nimport com.dss26.customer.events.ConsentGranted;\n"
           "import com.dss26.customer.events.ConsentType;\nimport com.dss26.customer.events.ProfileUpdated;"),
         S(CUS_EVENTS, "import java.time.Clock;\nimport java.util.List;",
           "import java.time.Clock;\nimport java.time.Instant;\nimport java.util.List;"),
         S(CUS_EVENTS, '    static final String PROFILE_UPDATED = "customer.profile.updated.v1";\n',
           '    static final String PROFILE_UPDATED = "customer.profile.updated.v1";\n'
           '    static final String CONSENT_GRANTED = "customer.consent.granted.v1";\n'),
         S(CUS_EVENTS, "    private void afterCommit(",
           final(CUS, CUS_EVENTS, "    public void consentGranted(", "    }\n\n") + "    private void afterCommit("),
         Write(CUS_API, CUS_API_2022),
         Write("catalog-info.yaml", _cus_catalog(produces=("customer.profile.updated.v1", "customer.consent.granted.v1"), kyc=False)),
     )),
    ("2023-01-30 10:50", "lucas.moreau",
     "feat(onboarding): open the current account when KYC passes\n\n"
     "Consumer group customer-profile-svc on kyc.verification.completed.v1.\n"
     "On PASS, the core allocates the account number (core-banking-adapter,\n"
     "ACCTOPN1) and we publish customer.account.opened.v1. Redeliveries are\n"
     "detected by kyc_reference.\n\n"
     "Refs: CUST-288",
     (
         F(f"{CUS_PKG}/onboarding/KycVerifiedListener.java"),
         F("src/main/resources/db/migration/V3__customer_account.sql"),
         *avro("src/main/avro", "kyc.verification.completed.v1", "customer.account.opened.v1"),
         S(CUS_EVENTS, "import com.dss26.customer.events.ChangedBy;",
           "import com.dss26.customer.events.AccountOpened;\nimport com.dss26.customer.events.ChangedBy;"),
         S(CUS_EVENTS, "TransactionSynchronizationManager;\n\nimport java.time.Clock;",
           "TransactionSynchronizationManager;\n\nimport java.math.BigDecimal;\nimport java.time.Clock;"),
         S(CUS_EVENTS, "public class CustomerEvents {\n\n    static final String PROFILE_UPDATED",
           'public class CustomerEvents {\n\n    static final String ACCOUNT_OPENED = "customer.account.opened.v1";\n'
           "    static final String PROFILE_UPDATED"),
         S(CUS_EVENTS, "    private void afterCommit(",
           final(CUS, CUS_EVENTS, "    public void accountOpened(", "    }\n\n") + "    private void afterCommit("),
         S(CUS_YML, "        use.latest.version: true\n",
           final(CUS, CUS_YML, "        use.latest.version: true\n", "CORE_BANKING_ADAPTER_URL:http://core-banking-adapter.core-banking.svc:8080}\n")),
         Write("catalog-info.yaml", _cus_catalog(produces=CUS_PRODUCES, kyc=True)),
     )),
    ("2023-07-24 09:30", "lucas.moreau",
     "feat(consent): AISP re-authentication every 180 days\n\n"
     "The amended PSD2 RTS applies from 25 July 2023: account information\n"
     "access needs strong customer authentication every 180 days instead of\n"
     "90. New AISP grants get the longer validity; existing ones keep theirs.\n\n"
     "Refs: CUST-331",
     (
         S(CUS_CONSENT,
           "    /** PSD2 RTS article 10: account information access needs SCA again every 90 days. */\n"
           "    static final Duration AISP_VALIDITY = Duration.ofDays(90);\n",
           "    /** PSD2 RTS (as amended in 2023): account information access needs SCA again every 180 days. */\n"
           "    static final Duration AISP_VALIDITY = Duration.ofDays(180);\n"),
     )),
    ("2023-11-20 15:15", "aiko.tanaka",
     "feat(gdpr): erasure on request, after the retention periods\n\n"
     "Article 17 requests were handled by hand in the CRM. Erasure overwrites\n"
     "personal fields and keeps the customer id so ledger and audit\n"
     "references stay valid; it is refused while an account is open or was\n"
     "closed less than five years ago (AML record keeping).\n\n"
     "Refs: CUST-402",
     (F(f"{CUS_PKG}/gdpr/ErasureService.java"), F(CUS_API))),
    ("2024-04-22 10:40", "lucas.moreau",
     "chore: Spring Boot 3.2 and Java 21\n\n"
     "No javax imports to migrate. Flyway 10 needs flyway-database-postgresql.",
     (
         S("pom.xml", CUS_PARENT.format("2.6.7"), CUS_PARENT.format("3.2.5")),
         S("pom.xml", "<java.version>17</java.version>", "<java.version>21</java.version>"),
         S("pom.xml", "<confluent.version>7.1.1</confluent.version>", "<confluent.version>7.6.0</confluent.version>"),
         S("pom.xml", "<avro.version>1.11.0</avro.version>", "<avro.version>1.11.3</avro.version>"),
         S("pom.xml", "      <artifactId>flyway-core</artifactId>", "      <artifactId>flyway-database-postgresql</artifactId>"),
         S(".github/workflows/ci.yml", 'java-version: "17"', 'java-version: "21"'),
     )),
    ("2025-01-13 08:20", "platform-bot",
     "chore(deps): bump the maven group with 3 updates\n\n"
     "spring-boot-starter-parent 3.2.5 -> 3.4.1, kafka-avro-serializer\n"
     "7.6.0 -> 7.8.0, avro 1.11.3 -> 1.11.4.",
     (
         S("pom.xml", CUS_PARENT.format("3.2.5"), CUS_PARENT.format("3.4.1")),
         S("pom.xml", "<confluent.version>7.6.0</confluent.version>", "<confluent.version>7.8.0</confluent.version>"),
         S("pom.xml", "<avro.version>1.11.3</avro.version>", "<avro.version>1.11.4</avro.version>"),
     )),
    ("2026-04-13 14:05", "lucas.moreau",
     "docs(readme): API, events and privacy rules",
     (F("README.md"),)),
)

CUS_SPEC = RepoSpec(
    name=CUS,
    description="Customer master: profile, contact data, consents and account opening after KYC.",
    team="customer-platform",
    domain="customer",
    tier="C",
    topics=("team-customer-platform", "domain-customer", "java", "spring-boot", "kafka", "gdpr"),
    history=CUS_HISTORY,
    labels=DEFAULT_LABELS + (L_KAFKA, Label("privacy", "5319e7", "Personal data - needs a DPO review")),
)

# ===========================================================================
# Tier C - mobile-banking-app (digital-channels, React Native / TypeScript)
# ===========================================================================

MOB = "mobile-banking-app"
MOB_TX = "src/screens/TransactionsScreen.tsx"
MOB_CTRL = "src/screens/CardControlsScreen.tsx"
MOB_CARDS = "src/api/cards.ts"
MOB_MONEY = "src/utils/money.ts"
MOB_MONEY_TEST = "__tests__/money.test.ts"


def _mob_catalog(*, pagerduty: bool) -> str:
    return catalog_info(
        MOB,
        title="DSS26 Bank mobile app",
        description="iOS and Android banking app (React Native) for retail customers.",
        owner="digital-channels", system="digital-banking", type="mobile-app",
        tags=("react-native", "typescript", "ios", "android", "tier-1"),
        pagerduty="PSVC4ZL" if pagerduty else None,
        opsgenie=None if pagerduty else "Digital Channels",
        dashboard=dd("w4n-6ty-j1d", "mobile-app"),
        depends_on=("component:mobile-bff",),
    )


MOB_A11Y = (
    S(MOB_TX, "import {signedAmount} from '../utils/money';", "import {signedAmount, spokenAmount} from '../utils/money';"),
    S(MOB_TX, "    <View style={styles.row}>\n",
      final(MOB, MOB_TX, "    <View\n      style={styles.row}", "}`}>\n")),
    S(MOB_TX, "    return <ActivityIndicator style={styles.loading} />;",
      '    return <ActivityIndicator style={styles.loading} accessibilityLabel="Loading transactions" />;'),
    S(MOB_TX, "      <Text style={styles.error}>", '      <Text style={styles.error} accessibilityRole="alert">'),
    S(MOB_TX, "      refreshing={query.isRefetching}\n    />",
      '      refreshing={query.isRefetching}\n      accessibilityRole="list"\n    />'),
    S(MOB_TX, "  row: {flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12},",
      "  row: {flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, minHeight: 56},"),
    S(MOB_CTRL, '          accessibilityLabel="Freeze card"\n        />',
      final(MOB, MOB_CTRL, '          accessibilityLabel="Freeze card"\n', "        />")),
    S(MOB_CTRL, "  row: {flexDirection: 'row', alignItems: 'center'},",
      "  row: {flexDirection: 'row', alignItems: 'center', minHeight: 48},"),
    S(MOB_MONEY, final(MOB, MOB_MONEY, "/** Debits show", "`;\n}\n"),
      final(MOB, MOB_MONEY, "/** Debits show", "minus ${formatted}`;\n}\n")),
    S(MOB_MONEY_TEST, "  it('falls back to the raw value",
      final(MOB, MOB_MONEY_TEST, "  it('spells the sign out", "  });\n\n") + "  it('falls back to the raw value"),
)

MOB_KEYSET = (
    S(MOB_TX,
      "    queryFn: ({pageParam}) => fetchTransactions(cardToken, pageParam),\n"
      "    initialPageParam: 0,\n"
      "    getNextPageParam: last => (last.hasMore ? last.page + 1 : undefined),\n",
      "    queryFn: ({pageParam}) => fetchTransactions(cardToken, pageParam),\n"
      "    initialPageParam: null as string | null,\n"
      "    getNextPageParam: last => last.nextBefore,\n"),
    S(MOB_CARDS,
      "export interface TransactionPage {\n  items: CardTransaction[];\n  page: number;\n  hasMore: boolean;\n}\n\n"
      "export function fetchTransactions(cardToken: string, page: number): Promise<TransactionPage> {\n"
      "  return api<TransactionPage>(`/cards/${cardToken}/transactions?page=${page}&size=50`);\n}\n",
      final(MOB, MOB_CARDS, "export interface TransactionPage {", "transactions${query}`);\n}\n")),
    S("README.md", "- Transactions are paged (`page`, 50 per page).\n",
      "- Transactions page with a cursor (`nextBefore`) since DIG-702.\n"),
)

# React Native 0.76 / React Query 5 version of the screen, before accessibility and cursor paging.
MOB_TX_2025 = rewind(MOB, MOB_TX, *[s for s in MOB_A11Y + MOB_KEYSET if s.path == MOB_TX])
MOB_TX_2023 = MOB_TX_2025.replace(
    "    queryFn: ({pageParam}) => fetchTransactions(cardToken, pageParam),\n    initialPageParam: 0,\n",
    "    queryFn: ({pageParam = 0}) => fetchTransactions(cardToken, pageParam),\n",
).replace("  if (query.isPending) {", "  if (query.isLoading) {")
assert MOB_TX_2023 != MOB_TX_2025

MOB_README_2020 = """\
# mobile-banking-app

The DSS26 Bank app for iOS and Android, in React Native.

## Development

```bash
npm ci
npm run ios      # or: npm run android
npm test
```

Environment settings (`BFF_BASE_URL`) come from the Digital Channels vault
entry; never commit them.

- Transactions are paged (`page`, 50 per page).

## On-call

Paging: Opsgenie team "Digital Channels".
"""

MOB_PACKAGE_2020 = """\
{
  "name": "dss26-mobile-banking",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "android": "react-native run-android",
    "ios": "react-native run-ios",
    "start": "react-native start",
    "lint": "eslint . --ext .ts,.tsx",
    "typecheck": "tsc --noEmit",
    "test": "jest"
  },
  "dependencies": {
    "@react-navigation/native": "^5.7.3",
    "@react-navigation/stack": "^5.9.0",
    "react": "16.13.1",
    "react-native": "0.63.2",
    "react-native-config": "^1.3.3",
    "react-native-gesture-handler": "^1.7.0",
    "react-native-safe-area-context": "^3.1.4",
    "react-native-screens": "^2.10.1"
  },
  "devDependencies": {
    "@babel/core": "^7.11.1",
    "@react-native-community/eslint-config": "^2.0.0",
    "@types/jest": "^26.0.9",
    "@types/react-native": "^0.63.4",
    "babel-jest": "^26.3.0",
    "eslint": "^7.6.0",
    "jest": "^26.4.0",
    "metro-react-native-babel-preset": "^0.59.0",
    "typescript": "^3.9.7"
  },
  "jest": {
    "preset": "react-native"
  }
}
"""

MOB_TSCONFIG_2020 = """\
{
  "compilerOptions": {
    "target": "esnext",
    "module": "commonjs",
    "lib": ["es2017"],
    "allowJs": true,
    "jsx": "react-native",
    "noEmit": true,
    "isolatedModules": true,
    "strict": true,
    "moduleResolution": "node",
    "allowSyntheticDefaultImports": true,
    "esModuleInterop": true
  },
  "exclude": ["node_modules", "babel.config.js", "metro.config.js", "jest.config.js"]
}
"""

MOB_CI_2020 = """\
name: ci

on:
  pull_request:

jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-node@v2
        with:
          node-version: 14
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm test -- --ci
"""

MOB_APP_2020 = """\
import React from 'react';
import {SafeAreaView, StatusBar, Text} from 'react-native';
import {NavigationContainer} from '@react-navigation/native';
import {createStackNavigator} from '@react-navigation/stack';

const Stack = createStackNavigator();

function Home() {
  return (
    <SafeAreaView>
      <StatusBar barStyle="dark-content" />
      <Text>DSS26 Bank</Text>
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="Home" component={Home} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
"""

MOB_APP_2022 = """\
import React from 'react';
import {NavigationContainer} from '@react-navigation/native';
import {createStackNavigator} from '@react-navigation/stack';
import CardControlsScreen from './screens/CardControlsScreen';

const Stack = createStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="CardControls" component={CardControlsScreen as never} options={{title: 'Card controls'}} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
"""

MOB_APP_2023 = """\
import React from 'react';
import {NavigationContainer} from '@react-navigation/native';
import {createStackNavigator} from '@react-navigation/stack';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import TransactionsScreen from './screens/TransactionsScreen';
import CardControlsScreen from './screens/CardControlsScreen';

const Stack = createStackNavigator();
const queryClient = new QueryClient({defaultOptions: {queries: {staleTime: 30_000, retry: 1}}});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <NavigationContainer>
        <Stack.Navigator>
          <Stack.Screen name="Transactions" component={TransactionsScreen as never} />
          <Stack.Screen name="CardControls" component={CardControlsScreen as never} options={{title: 'Card controls'}} />
        </Stack.Navigator>
      </NavigationContainer>
    </QueryClientProvider>
  );
}
"""

MOB_CARDS_2022 = """\
import {api} from './client';

/** Temporary freeze: the only block the customer can lift themselves. */
export function freezeCard(cardToken: string): Promise<void> {
  return api<void>(`/cards/${cardToken}/freeze`, {method: 'POST'});
}

export function unfreezeCard(cardToken: string): Promise<void> {
  return api<void>(`/cards/${cardToken}/freeze`, {method: 'DELETE'});
}

export function reportLostOrStolen(cardToken: string, reason: 'LOST' | 'STOLEN'): Promise<void> {
  return api<void>(`/cards/${cardToken}/block`, {method: 'POST', body: JSON.stringify({reason})});
}
"""

MOB_GITIGNORE = "node_modules/\nios/Pods/\nandroid/.gradle/\n*.keystore\n.env*\n!.env.example\n"

MOB_HISTORY = history(
    MOB,
    ("2020-07-06 10:00", "zara.ahmed",
     "feat: React Native app shell\n\n"
     "One codebase for iOS and Android instead of the two agency-built apps.\n"
     "TypeScript, react-navigation, and a single API client that only talks\n"
     "to the mobile BFF.\n\n"
     "Refs: DIG-101",
     (
         Write("README.md", MOB_README_2020),
         Write("catalog-info.yaml", _mob_catalog(pagerduty=False)),
         Write(".github/CODEOWNERS", "* @dss26-org/digital-channels\n"),
         Write(".github/workflows/ci.yml", MOB_CI_2020),
         Write(".gitignore", MOB_GITIGNORE),
         Write("package.json", MOB_PACKAGE_2020),
         Write("tsconfig.json", MOB_TSCONFIG_2020),
         Write("babel.config.js", "module.exports = {\n  presets: ['module:metro-react-native-babel-preset'],\n};\n"),
         Write(".eslintrc.js", "module.exports = {\n  root: true,\n  extends: '@react-native-community',\n};\n"),
         F("app.json"),
         F("index.js"),
         Write("src/App.tsx", MOB_APP_2020),
         F("src/api/client.ts"),
         F(MOB_MONEY),
         F(MOB_MONEY_TEST),
     )),
    ("2021-05-17 14:30", "zara.ahmed",
     "feat(auth): biometric unlock\n\n"
     "The refresh token goes into the Keychain / Android Keystore with\n"
     "biometric access control (current enrolment only), so unlocking the app\n"
     "is Face ID, Touch ID or fingerprint instead of the PIN every time.\n\n"
     "Refs: DIG-188",
     (
         F("src/auth/session.ts"),
         S("package.json", '    "react-native-gesture-handler": "^1.7.0",\n',
           '    "react-native-gesture-handler": "^1.7.0",\n    "react-native-keychain": "^7.0.0",\n'),
     )),
    ("2022-03-14 11:15", "zara.ahmed",
     "feat(cards): freeze and unfreeze from the app\n\n"
     "The most requested feature in the store reviews. Freeze is a customer\n"
     "block the customer can lift; lost or stolen is final and orders a\n"
     "replacement.\n\n"
     "Refs: DIG-311",
     (
         F(MOB_CTRL),
         Write(MOB_CARDS, MOB_CARDS_2022),
         Write("src/App.tsx", MOB_APP_2022),
     )),
    ("2023-02-27 16:00", "olivia.grant",
     "feat(cards): live card transactions\n\n"
     "Transactions now come from txn-history-builder through the BFF, seconds\n"
     "after the card is used, instead of yesterday's statement lines. Paged,\n"
     "50 at a time, pull to refresh.\n\n"
     "Refs: DIG-472",
     (
         Write(MOB_TX, MOB_TX_2023),
         F(MOB_CARDS),
         Write("src/App.tsx", MOB_APP_2023),
         S("package.json", '    "@react-navigation/stack": "^5.9.0",\n',
           '    "@react-navigation/stack": "^5.9.0",\n    "@tanstack/react-query": "^4.24.10",\n'),
     )),
    ("2025-01-27 10:20", "olivia.grant",
     "chore: React Native 0.76 (New Architecture), React Query 5, React Navigation 7\n\n"
     "0.76 makes the New Architecture the default; all our native modules\n"
     "support it now. Navigation moves to the native stack, React Query 5\n"
     "needs initialPageParam on infinite queries. Node 22 in CI.\n\n"
     "Refs: DIG-640",
     (
         F("package.json"),
         F("tsconfig.json"),
         F("babel.config.js"),
         F(".eslintrc.js"),
         F("src/App.tsx"),
         Write(MOB_TX, MOB_TX_2025),
         F(".github/workflows/ci.yml"),
     )),
    ("2025-03-24 09:10", "zara.ahmed",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired. Service PSVC4ZL, escalation policy\n"
     "\"Digital Channels - Primary\".",
     (
         Write("catalog-info.yaml", _mob_catalog(pagerduty=True)),
         S("README.md", 'Paging: Opsgenie team "Digital Channels".',
           'Paging: PagerDuty service `PSVC4ZL` ("Digital Channels - Primary").'),
     )),
    ("2025-05-26 15:45", "olivia.grant",
     "feat(a11y): WCAG 2.1 AA for transactions and card controls\n\n"
     "European Accessibility Act obligations start on 28 June. Screen readers\n"
     "now get one label per transaction row with the amount spelled out\n"
     "(\"minus\" instead of the glyph), errors are announced, the freeze switch\n"
     "has a hint, and touch targets are at least 48 dp. README describes the\n"
     "app as it is today.\n\n"
     "Refs: DIG-688",
     MOB_A11Y + (F("README.md"),)),
    ("2026-02-11 10:30", "zara.ahmed",
     "feat(transactions): cursor paging\n\n"
     "txn-history-builder replaced page numbers with a cursor on\n"
     "authorised_at (CSERV-597); the BFF passes nextBefore through. Heavy\n"
     "users no longer wait on deep pages.\n\n"
     "Refs: DIG-702",
     MOB_KEYSET),
)

MOB_SPEC = RepoSpec(
    name=MOB,
    description="DSS26 Bank mobile app for iOS and Android (React Native, TypeScript).",
    team="digital-channels",
    domain="digital",
    tier="C",
    topics=("team-digital-channels", "domain-digital", "react-native", "typescript", "mobile"),
    history=MOB_HISTORY,
    labels=DEFAULT_LABELS + (L_A11Y, Label("release-train", "c2e0c6", "Ships with the next fortnightly train")),
)

# ===========================================================================
# Tier C - internet-banking-web (digital-channels, TypeScript / React)
# ===========================================================================

WEB = "internet-banking-web"
WEB_APP = "src/App.tsx"
WEB_TX = "src/pages/TransactionsPage.tsx"
WEB_ST = "src/pages/StatementsPage.tsx"
WEB_HTTP = "src/api/http.ts"
WEB_I18N = "src/i18n/index.ts"


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{WEB}: expected one {old[:60]!r}, found {text.count(old)}")
    return text.replace(old, new, 1)


def _drop_block(text: str, start: str, end: str) -> str:
    """Remove the first block from ``start`` through the next ``end``."""
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[:i] + text[j:]


def _web_catalog(*, pagerduty: bool) -> str:
    return catalog_info(
        WEB,
        title="Internet banking",
        description="DSS26 Bank internet banking single-page app (React, Vite).",
        owner="digital-channels", system="digital-banking", type="website",
        tags=("typescript", "react", "vite", "tier-1"),
        pagerduty="PSVC1GV" if pagerduty else None,
        opsgenie=None if pagerduty else "Digital Channels",
        dashboard=dd("e7r-3gc-p0u", "internet-banking"),
        depends_on=("component:web-bff",),
    )


# --- accessibility (2025-06) -------------------------------------------------
WEB_A11Y = (
    S(WEB_APP, "    <>\n      <header>\n        <nav>\n",
      "    <>\n      <a className=\"skip-link\" href=\"#main\">\n        {t('nav.skip')}\n      </a>\n"
      "      <header>\n        <nav aria-label={t('nav.label')}>\n"),
    S(WEB_APP, "        <select value={i18n.language}", "        <select aria-label={t('nav.language')} value={i18n.language}"),
    S(WEB_APP, "      <main>\n", '      <main id="main">\n'),
    S(WEB_TX, "    <section>\n      <h1>{t('transactions.title')}</h1>\n",
      "    <section aria-labelledby=\"tx-title\">\n      <h1 id=\"tx-title\">{t('transactions.title')}</h1>\n"),
    S(WEB_TX,
      "      {query.isPending && <p>{t('common.loading')}</p>}\n"
      "      {query.isError && <p>{t('transactions.error')}</p>}\n",
      final(WEB, WEB_TX, '      <div aria-live="polite">', "      </div>\n")),
    S(WEB_TX,
      "        <table>\n          <thead>\n            <tr>\n"
      "              <th>{t('transactions.date')}</th>\n"
      "              <th>{t('transactions.merchant')}</th>\n"
      "              <th>{t('transactions.status')}</th>\n"
      "              <th className=\"num\">{t('transactions.amount')}</th>\n",
      final(WEB, WEB_TX, "        <table>\n", "{t('transactions.amount')}</th>\n")),
    S(WEB_ST, "    <section>\n      <h1>{t('statements.title')}</h1>\n      {statements.isError && <p>",
      "    <section aria-labelledby=\"st-title\">\n      <h1 id=\"st-title\">{t('statements.title')}</h1>\n"
      "      {statements.isError && <p role=\"alert\">"),
    S(WEB_ST, "            <a href={s.downloadUrl} download>",
      "            <a href={s.downloadUrl} download aria-label={t('statements.download', "
      "{period: formatPeriod(s.statementPeriod, i18n.language)})}>"),
    S("package.json", '    "eslint": "^9.16.0",\n', '    "eslint": "^9.16.0",\n    "eslint-plugin-jsx-a11y": "^6.10.2",\n'),
    S("eslint.config.js", "import tseslint from 'typescript-eslint';\n",
      "import tseslint from 'typescript-eslint';\nimport jsxA11y from 'eslint-plugin-jsx-a11y';\n"),
    S("eslint.config.js", "  ...tseslint.configs.recommended,\n",
      "  ...tseslint.configs.recommended,\n  jsxA11y.flatConfigs.recommended,\n"),
)

# --- cursor paging (2026-02) -------------------------------------------------
WEB_KEYSET = (
    S(WEB_TX,
      "    initialPageParam: 0,\n    getNextPageParam: last => (last.hasMore ? last.page + 1 : undefined),\n",
      "    initialPageParam: null as string | null,\n    getNextPageParam: last => last.nextBefore,\n"),
    S(WEB_HTTP, "  items: CardTransaction[];\n  page: number;\n  hasMore: boolean;\n}\n",
      "  items: CardTransaction[];\n  nextBefore: string | null;\n}\n"),
    S(WEB_HTTP,
      "export const fetchTransactions = (cardToken: string, page: number) =>\n"
      "  http<TransactionPage>(`/cards/${cardToken}/transactions?page=${page}`);\n",
      final(WEB, WEB_HTTP, "export const fetchTransactions", "encodeURIComponent(before)}` : ''}`);\n")),
    S("README.md", "`GET /cards/{token}/transactions?page=`", "`GET /cards/{token}/transactions?before=`"),
)


def _for(path: str, swaps: tuple[S, ...]) -> list[S]:
    return [s for s in swaps if s.path == path]


# App: 2024 (nl/de) -> 2023 (transactions) -> 2022 (statements only)
WEB_APP_2024 = rewind(WEB, WEB_APP, *_for(WEB_APP, WEB_A11Y))
WEB_APP_2023 = _replace_once(
    _replace_once(WEB_APP_2024, '          <option value="nl">Nederlands</option>\n', ""),
    '          <option value="de">Deutsch</option>\n', "")
WEB_APP_2022 = WEB_APP_2023
for _line in ("import TransactionsPage from './pages/TransactionsPage';\n",
              "          <Link to=\"/cards/transactions\">{t('nav.transactions')}</Link>\n",
              '          <Route path="/cards/transactions" element={<TransactionsPage />} />\n'):
    WEB_APP_2022 = _replace_once(WEB_APP_2022, _line, "")

# Transactions page: React Query 5 page-numbered (2025-01) and React Query 4 (2023).
WEB_TX_2025 = rewind(WEB, WEB_TX, *_for(WEB_TX, WEB_A11Y + WEB_KEYSET))
WEB_TX_2023 = _replace_once(
    _replace_once(WEB_TX_2025,
                  "    queryFn: ({pageParam}) => fetchTransactions(cardToken, pageParam),\n    initialPageParam: 0,\n",
                  "    queryFn: ({pageParam = 0}) => fetchTransactions(cardToken, pageParam),\n"),
    "      {query.isPending && <p>", "      {query.isLoading && <p>")

# http client before transactions existed.
WEB_HTTP_2025 = rewind(WEB, WEB_HTTP, *_for(WEB_HTTP, WEB_KEYSET))
WEB_HTTP_TX_TYPES = final(WEB, WEB_HTTP, "export interface CardTransaction {", "\n\n")  # interface + blank line
WEB_HTTP_TX_PAGE = WEB_HTTP_2025[WEB_HTTP_2025.index("export interface TransactionPage {"):
                                 WEB_HTTP_2025.index("export interface Statement {")]
WEB_HTTP_TX_FETCH = WEB_HTTP_2025[WEB_HTTP_2025.index("export const fetchTransactions"):
                                  WEB_HTTP_2025.index("export const fetchStatements")]

# i18n: strip the accessibility keys, then Dutch/German, then the transactions page.
WEB_I18N_2024 = (FILES_ROOT / WEB / WEB_I18N).read_text()
for _old, _new in (
        ("nav: {label: 'Main', skip: 'Skip to content', ", "nav: {"),
        ("nav: {label: 'Principal', skip: 'Aller au contenu', ", "nav: {"),
        ("nav: {label: 'Hoofdmenu', skip: 'Naar inhoud', ", "nav: {"),
        ("nav: {label: 'Hauptmenü', skip: 'Zum Inhalt', ", "nav: {"),
        (", language: 'Language'}", "}"), (", language: 'Langue'}", "}"),
        (", language: 'Taal'}", "}"), (", language: 'Sprache'}", "}"),
        (" caption: 'Card transactions, newest first',", ""),
        (" caption: 'Opérations carte, les plus récentes en premier',", ""),
        (" caption: 'Kaarttransacties, nieuwste eerst',", ""),
        (" caption: 'Kartenumsätze, neueste zuerst',", ""),
        (", download: 'Download statement for {{period}}'", ""),
        (", download: 'Télécharger le relevé de {{period}}'", ""),
        (", download: 'Afschrift van {{period}} downloaden'", ""),
        (", download: 'Kontoauszug {{period}} herunterladen'", "")):
    WEB_I18N_2024 = _replace_once(WEB_I18N_2024, _old, _new)
WEB_I18N_2023 = _drop_block(_drop_block(WEB_I18N_2024, "const nl = {", "};\n\n"), "const de = {", "};\n\n")
WEB_I18N_2023 = _replace_once(WEB_I18N_2023, ", nl: {translation: nl}, de: {translation: de}}", "}")
WEB_I18N_2022 = WEB_I18N_2023
for _old in ("transactions: 'Card transactions', ", "transactions: 'Opérations carte', "):
    WEB_I18N_2022 = _replace_once(WEB_I18N_2022, _old, "")
WEB_I18N_2022 = _drop_block(WEB_I18N_2022, "  transactions: {\n", "  },\n")
WEB_I18N_2022 = _drop_block(WEB_I18N_2022, "  transactions: {\n", "  },\n")
assert "transactions" not in WEB_I18N_2022

WEB_PACKAGE_2022 = """\
{
  "name": "internet-banking-web",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint src --ext .ts,.tsx",
    "test": "vitest run"
  },
  "dependencies": {
    "@tanstack/react-query": "^4.3.4",
    "i18next": "^21.9.1",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-i18next": "^11.18.5",
    "react-router-dom": "^6.3.0"
  },
  "devDependencies": {
    "@types/react": "^18.0.18",
    "@types/react-dom": "^18.0.6",
    "@typescript-eslint/eslint-plugin": "^5.36.1",
    "@typescript-eslint/parser": "^5.36.1",
    "@vitejs/plugin-react": "^2.0.1",
    "eslint": "^8.23.0",
    "jsdom": "^20.0.0",
    "typescript": "^4.8.2",
    "vite": "^3.0.9",
    "vitest": "^0.23.1"
  }
}
"""

WEB_ESLINTRC_2022 = """\
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint'],
  extends: ['eslint:recommended', 'plugin:@typescript-eslint/recommended'],
  ignorePatterns: ['dist/'],
};
"""

WEB_CI_2022 = """\
name: ci

on:
  pull_request:

jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 16
          cache: npm
      - run: npm ci
      - run: npm run lint
      - run: npm test
      - run: npm run build
"""

WEB_README_2022 = """\
# internet-banking-web

DSS26 Bank internet banking, React 18 and Vite, replacing the AngularJS
application. Served from the same origin as the web BFF (`/web/v1`).

## Development

```bash
npm ci
npm run dev
npm test
```

| Page | BFF route |
|------|-----------|
| Statements | `GET /cards/{token}/statements` |

## On-call

Paging: Opsgenie team "Digital Channels".
"""

WEB_HISTORY = history(
    WEB,
    ("2022-09-05 10:10", "zara.ahmed",
     "feat: new internet banking front end\n\n"
     "React 18 and Vite, same origin as the web BFF, so the session cookie\n"
     "stays HttpOnly and there is no CORS. English and French from day one.\n"
     "Statements are the first page to move off the AngularJS app.\n\n"
     "Refs: DIG-402",
     (
         Write("README.md", WEB_README_2022),
         Write("catalog-info.yaml", _web_catalog(pagerduty=False)),
         Write(".github/CODEOWNERS", "* @dss26-org/digital-channels\n"),
         Write(".github/workflows/ci.yml", WEB_CI_2022),
         Write(".gitignore", "node_modules/\ndist/\ncoverage/\n"),
         Write("package.json", WEB_PACKAGE_2022),
         Write(".eslintrc.cjs", WEB_ESLINTRC_2022),
         Write("tsconfig.json", _replace_once((FILES_ROOT / WEB / "tsconfig.json").read_text(),
                                              '"moduleResolution": "bundler"', '"moduleResolution": "node"')),
         F("vite.config.ts"),
         F("index.html"),
         F("src/main.tsx"),
         Write(WEB_APP, WEB_APP_2022),
         F(WEB_HTTP),
         F(WEB_ST),
         Write(WEB_I18N, WEB_I18N_2022),
         F("src/lib/format.ts"),
         F("src/lib/format.test.ts"),
     )),
    ("2023-03-06 14:40", "olivia.grant",
     "feat(cards): card transactions page\n\n"
     "Live card transactions from txn-history-builder through the web BFF,\n"
     "the same data the app shows. 50 per page, \"show older\" loads the next.\n\n"
     "Refs: DIG-478",
     (
         Write(WEB_TX, WEB_TX_2023),
         Write(WEB_APP, WEB_APP_2023),
         Write(WEB_I18N, WEB_I18N_2023),
         S(WEB_HTTP, "export interface Statement {",
           WEB_HTTP_TX_TYPES + WEB_HTTP_TX_PAGE + "export interface Statement {"),
         S(WEB_HTTP, "export const fetchStatements", WEB_HTTP_TX_FETCH + "export const fetchStatements"),
         S("README.md", "| Statements | `GET /cards/{token}/statements` |\n",
           "| Card transactions | `GET /cards/{token}/transactions?page=` |\n"
           "| Statements | `GET /cards/{token}/statements` |\n"),
     )),
    ("2024-02-19 11:20", "olivia.grant",
     "feat(i18n): Dutch and German\n\n"
     "For the Benelux and DACH customers moving over from the partner bank\n"
     "portfolio. Language follows the browser, switchable in the header.\n\n"
     "Refs: DIG-561",
     (Write(WEB_APP, WEB_APP_2024), Write(WEB_I18N, WEB_I18N_2024))),
    ("2025-01-06 15:30", "zara.ahmed",
     "chore: Vite 6, Vitest 2, React Query 5, ESLint 9\n\n"
     "React Query 5 needs initialPageParam on infinite queries and renames\n"
     "isLoading to isPending. ESLint 9 uses the flat config. TypeScript 5.6\n"
     "with bundler module resolution. Node 22 in CI.\n\n"
     "Refs: DIG-637",
     (
         F("package.json"),
         Delete(".eslintrc.cjs"),
         F("eslint.config.js"),
         F("tsconfig.json"),
         Write(WEB_TX, WEB_TX_2025),
         F(".github/workflows/ci.yml"),
     )),
    ("2025-03-24 09:15", "zara.ahmed",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired. Service PSVC1GV, escalation policy\n"
     "\"Digital Channels - Primary\".",
     (
         Write("catalog-info.yaml", _web_catalog(pagerduty=True)),
         S("README.md", 'Paging: Opsgenie team "Digital Channels".',
           'Paging: PagerDuty service `PSVC1GV` ("Digital Channels - Primary").'),
     )),
    ("2025-06-23 16:05", "olivia.grant",
     "feat(a11y): WCAG 2.1 AA for the card pages\n\n"
     "European Accessibility Act obligations start on 28 June. Skip link and\n"
     "labelled landmarks, table caption and column headers, loading and\n"
     "errors announced through aria-live, descriptive download links, and\n"
     "eslint-plugin-jsx-a11y in CI so it stays that way.\n\n"
     "Refs: DIG-690",
     WEB_A11Y + (F(WEB_I18N), F("README.md"))),
    ("2026-02-11 11:05", "zara.ahmed",
     "feat(transactions): cursor paging\n\n"
     "Same change as the app (DIG-702): the BFF now passes\n"
     "txn-history-builder's nextBefore cursor through instead of page numbers.\n\n"
     "Refs: DIG-702",
     WEB_KEYSET),
)

WEB_SPEC = RepoSpec(
    name=WEB,
    description="DSS26 Bank internet banking single-page app (React, Vite, TypeScript).",
    team="digital-channels",
    domain="digital",
    tier="C",
    topics=("team-digital-channels", "domain-digital", "typescript", "react", "vite"),
    history=WEB_HISTORY,
    labels=DEFAULT_LABELS + (L_A11Y,),
)

# ===========================================================================
# Tier C - core-banking-adapter (core-banking, Java)
# ===========================================================================

CBA = "core-banking-adapter"
CBA_PKG = "src/main/java/com/dss26/core/adapter"
CBA_QUEUES = f"{CBA_PKG}/mq/CoreQueues.java"
CBA_GATEWAY = f"{CBA_PKG}/mq/MqGateway.java"
CBA_LISTENER = f"{CBA_PKG}/ledger/JournalPostingListener.java"
CBA_YML = "src/main/resources/application.yml"
CBA_CI = ".github/workflows/ci.yml"
CBA_PARENT = "    <artifactId>spring-boot-starter-parent</artifactId>\n    <version>{}</version>"


def _cba_catalog(*, ledger: bool, pagerduty: bool) -> str:
    return catalog_info(
        CBA,
        title="Core banking adapter",
        description="MQ bridge to the core ledger on the mainframe: balances, account opening, GL postings.",
        owner="core-banking", system="core-banking",
        tags=("java", "spring-boot", "ibm-mq", "mainframe", "tier-1") + (("kafka",) if ledger else ()),
        pagerduty="PSVC5JB" if pagerduty else None,
        opsgenie=None if pagerduty else "Core Banking",
        dashboard=dd("x5c-1nt-g7w", CBA),
        consumes=("ledger.journal.posted.v1",) if ledger else (),
        groups=(CBA,) if ledger else (),
        depends_on=("resource:core-queue-manager",),
    )


CBA_POM_2020 = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>2.2.4.RELEASE</version>
    <relativePath/>
  </parent>

  <groupId>com.dss26.core</groupId>
  <artifactId>core-banking-adapter</artifactId>
  <version>4.2.0-SNAPSHOT</version>
  <description>Bridge between the bank's services and the core ledger on the mainframe (IBM MQ)</description>

  <properties>
    <java.version>11</java.version>
    <mq-starter.version>2.2.6</mq-starter.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>com.ibm.mq</groupId>
      <artifactId>mq-jms-spring-boot-starter</artifactId>
      <version>${mq-starter.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""

CBA_REPOS = final(CBA, "pom.xml", "  <repositories>", "  </repositories>\n\n")
CBA_KAFKA_DEPS = final(CBA, "pom.xml", "    <dependency>\n      <groupId>org.springframework.kafka</groupId>",
                       "      <version>${avro.version}</version>\n    </dependency>\n")
CBA_AVRO_PLUGIN = final(CBA, "pom.xml", "      <plugin>\n        <groupId>org.apache.avro</groupId>", "      </plugin>\n")

CBA_README_2020 = """\
# core-banking-adapter

The bridge between the bank's services and the core ledger on the mainframe,
over IBM MQ. Nothing else talks to the core queue manager.

| Interface | Copybook | Queues |
|-----------|----------|--------|
| `GET /v1/accounts/{account}/balance` | ACCTBAL1 | `DSS26.CORE.ACCT.BAL.REQ` / `.RPY` |

Copybooks in `copybooks/` are the contract with the mainframe team.

## Build

```bash
mvn -B verify
```

## On-call

Paging: Opsgenie team "Core Banking". Mainframe operations bridge: `#core-ops`.
"""

CBA_CI_2020 = """\
name: ci

on:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-java@v1
        with:
          java-version: "11"
      - name: Build and test
        run: mvn -B verify
"""

CBA_HISTORY = history(
    CBA,
    ("2020-02-03 10:00", "pieter.devries",
     "feat: real-time balance enquiry against the core over MQ\n\n"
     "The channels read balances from last night's extract. ACCTBAL1 is\n"
     "already served by the core for the branch terminals; this exposes it\n"
     "as REST behind the API gateway. Request/reply on the core queue\n"
     "manager, correlation id per request, 5 second timeout.\n\n"
     "Refs: CORE-341",
     (
         Write("README.md", CBA_README_2020),
         Write("catalog-info.yaml", _cba_catalog(ledger=False, pagerduty=False)),
         Write(".github/CODEOWNERS", "*            @dss26-org/core-banking\n/copybooks/  @dss26-org/core-banking @pieter.devries\n"),
         Write(CBA_CI, CBA_CI_2020),
         Write(".gitignore", GITIGNORE_MAVEN),
         Write("pom.xml", CBA_POM_2020),
         F("copybooks/ACCTBAL1.cpy"),
         F(f"{CBA_PKG}/CoreBankingAdapterApplication.java"),
         F(CBA_QUEUES),
         F(CBA_GATEWAY),
         F(f"{CBA_PKG}/balance/BalanceEnquiryController.java"),
         F(CBA_YML),
     )),
    ("2020-11-09 14:25", "pieter.devries",
     "fix(mq): reconnect to the standby queue manager\n\n"
     "During Saturday's failover test of the multi-instance queue manager the\n"
     "adapter kept retrying the old host until it was restarted. Both\n"
     "instances in the connection name, automatic client reconnect for up to\n"
     "30 minutes.\n\n"
     "Refs: CORE-388",
     (
         S(CBA_YML, "    conn-name: ${MQ_CONN_NAME:mqcore-a.core.dss26.internal(1414)}\n",
           "    # Multi-instance queue manager: the client reconnects to whichever is active.\n"
           "    conn-name: ${MQ_CONN_NAME:mqcore-a.core.dss26.internal(1414),mqcore-b.core.dss26.internal(1414)}\n"),
         S(CBA_YML, "    ssl-cipher-spec: TLS_AES_256_GCM_SHA384\n",
           "    ssl-cipher-spec: TLS_AES_256_GCM_SHA384\n    client-reconnect-options: QMGR\n    reconnect-timeout: 1800\n"),
     )),
    ("2021-06-14 11:10", "pieter.devries",
     "feat(accounts): open accounts in the core (ACCTOPN1)\n\n"
     "Digital onboarding needs an account number at the end of the journey,\n"
     "not the next morning. The core allocates it; the correlation id is\n"
     "customer + product so a retried call returns the same account.\n\n"
     "Refs: CORE-455",
     (
         F("copybooks/ACCTOPN1.cpy"),
         F(f"{CBA_PKG}/accounts/AccountOpeningController.java"),
         S(CBA_QUEUES, '    public static final String BALANCE_REPLY = "DSS26.CORE.ACCT.BAL.RPY";\n',
           '    public static final String BALANCE_REPLY = "DSS26.CORE.ACCT.BAL.RPY";\n'
           '    public static final String OPEN_REQUEST = "DSS26.CORE.ACCT.OPEN.REQ";\n'
           '    public static final String OPEN_REPLY = "DSS26.CORE.ACCT.OPEN.RPY";\n'),
         S("README.md", "| `GET /v1/accounts/{account}/balance` | ACCTBAL1 | `DSS26.CORE.ACCT.BAL.REQ` / `.RPY` |\n",
           "| `GET /v1/accounts/{account}/balance` | ACCTBAL1 | `DSS26.CORE.ACCT.BAL.REQ` / `.RPY` |\n"
           "| `POST /v1/accounts` | ACCTOPN1 | `DSS26.CORE.ACCT.OPEN.REQ` / `.RPY` |\n"),
     )),
    ("2022-06-20 15:30", "giulia.conti",
     "feat(ledger): post ledger.journal.posted.v1 to the core GL\n\n"
     "Card settlement journals reached the core GL through a nightly file.\n"
     "Consumer group core-banking-adapter now posts each journal as a GLPOST01\n"
     "record (EBCDIC, amount as COMP-3), one at a time per partition; a\n"
     "rejected posting stops the partition instead of skipping it.\n\n"
     "Refs: CORE-562",
     (
         F("copybooks/GLPOST01.cpy"),
         F(f"{CBA_PKG}/ledger/GlPostingEncoder.java"),
         F(CBA_LISTENER),
         F("src/test/java/com/dss26/core/adapter/ledger/GlPostingEncoderTest.java"),
         *avro("src/main/avro", "ledger.journal.posted.v1"),
         S(CBA_QUEUES, '    public static final String OPEN_REPLY = "DSS26.CORE.ACCT.OPEN.RPY";\n',
           '    public static final String OPEN_REPLY = "DSS26.CORE.ACCT.OPEN.RPY";\n'
           '    public static final String GL_POST_REQUEST = "DSS26.CORE.GL.POST.REQ";\n'
           '    public static final String GL_POST_REPLY = "DSS26.CORE.GL.POST.RPY";\n'),
         S("pom.xml", CBA_PARENT.format("2.2.4.RELEASE"), CBA_PARENT.format("2.7.0")),
         S("pom.xml", "<mq-starter.version>2.2.6</mq-starter.version>",
           "<mq-starter.version>2.7.1</mq-starter.version>\n"
           "    <confluent.version>7.1.1</confluent.version>\n    <avro.version>1.11.0</avro.version>"),
         S("pom.xml", "  </properties>\n\n  <dependencies>", "  </properties>\n\n" + CBA_REPOS + "  <dependencies>"),
         S("pom.xml", "    <dependency>\n      <groupId>org.springframework.boot</groupId>\n      <artifactId>spring-boot-starter-test</artifactId>",
           CBA_KAFKA_DEPS + "    <dependency>\n      <groupId>org.springframework.boot</groupId>\n"
           "      <artifactId>spring-boot-starter-test</artifactId>"),
         S("pom.xml", "    <plugins>\n      <plugin>\n        <groupId>org.springframework.boot</groupId>",
           "    <plugins>\n" + CBA_AVRO_PLUGIN + "      <plugin>\n        <groupId>org.springframework.boot</groupId>"),
         S(CBA_YML, "    name: core-banking-adapter\n\nibm:",
           final(CBA, CBA_YML, "    name: core-banking-adapter\n", "      ack-mode: record\n\nibm:")),
         S("README.md", "| `POST /v1/accounts` | ACCTOPN1 | `DSS26.CORE.ACCT.OPEN.REQ` / `.RPY` |\n",
           "| `POST /v1/accounts` | ACCTOPN1 | `DSS26.CORE.ACCT.OPEN.REQ` / `.RPY` |\n"
           "| `ledger.journal.posted.v1` (group `core-banking-adapter`) | GLPOST01 | `DSS26.CORE.GL.POST.REQ` / `.RPY` |\n"),
         Write("catalog-info.yaml", _cba_catalog(ledger=True, pagerduty=False)),
     )),
    ("2023-05-15 10:45", "pieter.devries",
     "chore: Spring Boot 3 and Java 17 (jakarta.jms)\n\n"
     "Boot 2.7 support ends in November. The MQ starter 3.x is built on\n"
     "jakarta.jms; the only code change is the imports in MqGateway.",
     (
         S("pom.xml", CBA_PARENT.format("2.7.0"), CBA_PARENT.format("3.0.6")),
         S("pom.xml", "<java.version>11</java.version>", "<java.version>17</java.version>"),
         S("pom.xml", "<mq-starter.version>2.7.1</mq-starter.version>", "<mq-starter.version>3.0.4</mq-starter.version>"),
         S("pom.xml", "<confluent.version>7.1.1</confluent.version>", "<confluent.version>7.3.3</confluent.version>"),
         S("pom.xml", "<avro.version>1.11.0</avro.version>", "<avro.version>1.11.1</avro.version>"),
         S(CBA_GATEWAY, "import javax.jms.BytesMessage;\nimport javax.jms.JMSException;\nimport javax.jms.Message;",
           "import jakarta.jms.BytesMessage;\nimport jakarta.jms.JMSException;\nimport jakarta.jms.Message;"),
         S(CBA_CI, '      - uses: actions/checkout@v2\n      - uses: actions/setup-java@v1\n        with:\n          java-version: "11"\n',
           '      - uses: actions/checkout@v3\n      - uses: actions/setup-java@v3\n        with:\n'
           '          distribution: temurin\n          java-version: "17"\n          cache: maven\n'),
     )),
    ("2024-03-11 16:20", "giulia.conti",
     "fix(ledger): one correlation id per journal, and RC 02 is a success\n\n"
     "A consumer rebalance during the batch window redelivered 31 journals;\n"
     "with a random correlation id per attempt the core posted them twice and\n"
     "GL reconciliation caught it the next morning. The correlation id is now\n"
     "derived from journal_id, so the core's duplicate log answers a retry\n"
     "with RC 02 (already posted), which we treat as success.\n\n"
     "Refs: CORE-731",
     (
         S(CBA_LISTENER, "import java.time.LocalDate;\nimport java.util.UUID;\n", "import java.time.LocalDate;\n"),
         S(CBA_LISTENER,
           "        byte[] reply = mq.requestReply(CoreQueues.GL_POST_REQUEST, CoreQueues.GL_POST_REPLY, record,\n"
           "                UUID.randomUUID().toString());\n"
           "        String returnCode = new String(reply, 0, 2, EBCDIC);\n"
           "        if (!\"00\".equals(returnCode)) {\n",
           final(CBA, CBA_LISTENER, "        // Correlation id = journal id", "!\"02\".equals(returnCode)) {\n")),
     )),
    ("2024-06-17 09:40", "pieter.devries",
     "chore: Java 21",
     (S("pom.xml", "<java.version>17</java.version>", "<java.version>21</java.version>"),
      S(CBA_CI, 'java-version: "17"', 'java-version: "21"'))),
    ("2025-03-24 09:30", "pieter.devries",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired. Service PSVC5JB, escalation policy\n"
     "\"Core Banking - Primary\".",
     (
         Write("catalog-info.yaml", _cba_catalog(ledger=True, pagerduty=True)),
         S("README.md", 'Paging: Opsgenie team "Core Banking".',
           'Paging: PagerDuty service `PSVC5JB` ("Core Banking - Primary").'),
     )),
    ("2025-09-08 07:40", "platform-bot",
     "chore(deps): bump the maven group with 4 updates\n\n"
     "spring-boot-starter-parent 3.0.6 -> 3.4.1, mq-jms-spring-boot-starter\n"
     "3.0.4 -> 3.4.1, kafka-avro-serializer 7.3.3 -> 7.8.0, avro 1.11.1 -> 1.11.4.",
     (F("pom.xml"),)),
    ("2026-04-20 13:15", "giulia.conti",
     "docs(readme): interfaces, idempotency and the batch window\n\n"
     "Most questions in #core-banking are about lag during the core's batch\n"
     "window and about duplicate postings. Both are answered here now.",
     (F("README.md"), F(CBA_CI))),
)

CBA_SPEC = RepoSpec(
    name=CBA,
    description="IBM MQ bridge to the core ledger: balance enquiry, account opening, GL postings from Kafka.",
    team="core-banking",
    domain="core-banking",
    tier="C",
    topics=("team-core-banking", "domain-core-banking", "java", "spring-boot", "ibm-mq", "kafka", "mainframe"),
    history=CBA_HISTORY,
    labels=DEFAULT_LABELS + (Label("copybook", "e99695", "Changes a mainframe copybook - needs a CORE change request"),),
)

# ===========================================================================
# Tier C - payments-hub (core-banking, Java)
# ===========================================================================

PH = "payments-hub"
PH_PKG = "src/main/java/com/dss26/payments/hub"
PH_SCHEME = f"{PH_PKG}/routing/Scheme.java"
PH_ROUTER = f"{PH_PKG}/routing/SchemeRouter.java"
PH_ROUTER_TEST = "src/test/java/com/dss26/payments/hub/routing/SchemeRouterTest.java"
PH_CONTROLLER = f"{PH_PKG}/api/PaymentController.java"
PH_PACS = f"{PH_PKG}/iso20022/Pacs008Builder.java"
PH_YML = "src/main/resources/application.yml"
PH_DOCS = "docs/schemes.md"


def _ph_text(path: str) -> str:
    return (FILES_ROOT / PH / path).read_text()


def _ph_edit(text: str, *pairs: tuple[str, str]) -> str:
    for old, new in pairs:
        if text.count(old) != 1:
            raise ValueError(f"{PH}: expected one {old[:60]!r}, found {text.count(old)}")
        text = text.replace(old, new, 1)
    return text


def _ph_catalog(*, pagerduty: bool) -> str:
    return catalog_info(
        PH,
        title="Payments hub",
        description="Outgoing credit transfers: SEPA SCT and SCT Inst, T2, SWIFT CBPR+ (ISO 20022 pacs.008).",
        owner="core-banking", system="payment-rails",
        tags=("java", "spring-boot", "iso20022", "sepa", "swift", "tier-1"),
        pagerduty="PSVC7EQ" if pagerduty else None,
        opsgenie=None if pagerduty else "Core Banking",
        dashboard=dd("q8v-5hd-n3e", PH),
        depends_on=("component:sanctions-screening-svc", "component:core-banking-adapter"),
    )


# --- Scheme enum through the years -------------------------------------------
PH_SCHEME_2020 = """\
package com.dss26.payments.hub.routing;

public enum Scheme {
    /** SEPA Credit Transfer, via STEP2 (D+1). */
    SCT,
    /** SWIFT FIN MT103, translated by the payments gateway from our pacs.008. */
    SWIFT
}
"""
PH_SCHEME_2020_INST = _ph_edit(PH_SCHEME_2020, (
    "    SCT,\n", "    SCT,\n    /** SEPA Instant Credit Transfer, via RT1 (10 seconds). */\n    SCT_INST,\n"))

# --- SchemeRouter --------------------------------------------------------------
_PH_ROUTER_FINAL = _ph_text(PH_ROUTER)
PH_ROUTER_2023 = _ph_edit(
    _PH_ROUTER_FINAL,
    (final(PH, PH_ROUTER, "/**\n * Picks the clearing scheme", " */\n"),
     "/** Picks the clearing scheme for an outgoing credit transfer. */\n"),
    ("    /** Above this, EUR payments go to T2",
     "    /** EPC SCT Inst rulebook maximum per transaction. */\n"
     "    static final BigDecimal SCT_INST_MAX = new BigDecimal(\"100000.00\");\n\n"
     "    /** Above this, EUR payments go to T2"),
    ("        if (instantRequested) {", "        if (instantRequested && amount.compareTo(SCT_INST_MAX) <= 0) {"),
)
PH_ROUTER_2020_INST = _ph_edit(
    PH_ROUTER_2023,
    (final(PH, PH_ROUTER, "    /** Above this, EUR payments go to T2", "new BigDecimal(\"1000000.00\");\n\n"), ""),
    ("        if (urgent || amount.compareTo(HIGH_VALUE_EUR) >= 0) {\n            return Scheme.T2;\n        }\n", ""),
    ("            return Scheme.SWIFT_CBPR;", "            return Scheme.SWIFT;"),
)
PH_ROUTER_2020 = _ph_edit(
    PH_ROUTER_2020_INST,
    ("    /** EPC SCT Inst rulebook maximum per transaction. */\n"
     "    static final BigDecimal SCT_INST_MAX = new BigDecimal(\"100000.00\");\n\n", ""),
    ("        if (instantRequested && amount.compareTo(SCT_INST_MAX) <= 0) {\n            return Scheme.SCT_INST;\n        }\n", ""),
)

PH_ROUTER_TEST_2020 = """\
package com.dss26.payments.hub.routing;

import com.dss26.payments.hub.iban.Iban;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

class SchemeRouterTest {

    private static final Iban DE = Iban.parse("DE89370400440532013000");
    private static final Iban GB = Iban.parse("GB29NWBK60161331926819");

    @Test
    void euroToSepaIsSct() {
        assertThat(SchemeRouter.route(DE, "EUR", new BigDecimal("250.00"), false, false)).isEqualTo(Scheme.SCT);
    }

    @Test
    void nonEuroGoesToSwift() {
        assertThat(SchemeRouter.route(GB, "GBP", new BigDecimal("80.00"), false, false)).isEqualTo(Scheme.SWIFT);
    }
}
"""
PH_ROUTER_TEST_2020_INST = _ph_edit(PH_ROUTER_TEST_2020, (
    "    @Test\n    void nonEuroGoesToSwift()",
    "    @Test\n    void instantUpToTheSchemeMaximum() {\n"
    "        assertThat(SchemeRouter.route(DE, \"EUR\", new BigDecimal(\"250.00\"), true, false)).isEqualTo(Scheme.SCT_INST);\n"
    "        assertThat(SchemeRouter.route(DE, \"EUR\", new BigDecimal(\"150000.00\"), true, false)).isEqualTo(Scheme.SCT);\n"
    "    }\n\n    @Test\n    void nonEuroGoesToSwift()"))
PH_ROUTER_TEST_2023 = _ph_edit(
    PH_ROUTER_TEST_2020_INST,
    ("    @Test\n    void nonEuroGoesToSwift()",
     final(PH, PH_ROUTER_TEST, "    @Test\n    void urgentOrHighValueEuroGoesToT2", "    }\n\n") + "    @Test\n    void nonEuroGoesToSwift()"),
    (").isEqualTo(Scheme.SWIFT);", ").isEqualTo(Scheme.SWIFT_CBPR);"),
)

# --- PaymentController: 2020 (route and send), 2024 (+ sanctions), final (+ VoP) --
_PH_CONTROLLER_FINAL = _ph_text(PH_CONTROLLER)
PH_CONTROLLER_2024 = _ph_edit(
    _PH_CONTROLLER_FINAL,
    ("import com.dss26.payments.hub.vop.VerificationOfPayeeService;\n", ""),
    ("    private final VerificationOfPayeeService vop;\n", ""),
    (", VerificationOfPayeeService vop", ""),
    ("        this.vop = vop;\n", ""),
    (final(PH, PH_CONTROLLER, "    /** Step 1 of the channel flow", "    }\n\n"), ""),
    ("    /** Step 2: the customer confirmed; route, screen and send. */",
     "    /** The customer confirmed the payment in the channel: route, screen and send. */"),
)
PH_CONTROLLER_2020 = _ph_edit(
    PH_CONTROLLER_2024,
    ("import com.dss26.payments.hub.screening.SanctionsScreeningClient;\n", ""),
    ("    private final SanctionsScreeningClient sanctions;\n", ""),
    ("SanctionsScreeningClient sanctions, ", ""),
    ("        this.sanctions = sanctions;\n", ""),
    (final(PH, PH_CONTROLLER, "        if (scheme == Scheme.SWIFT_CBPR", "        }\n\n"), ""),
    ("route, screen and send. */", "route and send. */"),
)

PH_PACS_DOC_2020 = """\
/**
 * Builds the interbank pacs.008 (FI to FI customer credit transfer). SEPA
 * usage rules (character set, mandatory fields) are enforced before this
 * point, in PaymentController. For SWIFT the payments gateway translates it
 * into an MT103.
 */
"""

PH_YML_2020 = """\
spring:
  application:
    name: payments-hub
  artemis:
    mode: native
    broker-url: ${PAYMENTS_GATEWAY_BROKER_URL}
    user: ${PAYMENTS_GATEWAY_USER}
    password: ${PAYMENTS_GATEWAY_PASSWORD}

hub:
  # Clearing and settlement mechanisms per scheme (gateway queue -> CSM).
  csm:
    sct: STEP2
    swift: SWIFTNET-FIN
"""

PH_SANCTIONS_URL = "    base-url: ${HUB_SANCTIONS_URL:http://sanctions-screening-svc.compliance-platform.svc:8080}\n"
PH_MT_FALLBACK = ("    swift: SWIFTNET-FINPLUS\n"
                  "    # Correspondents not yet on CBPR+ get an MT103 translated by the gateway.\n"
                  "    mt103-fallback: true\n")

PH_DOCS_SWIFT_2023 = (
    "- SWIFT: CBPR+ pacs.008. Correspondents not yet on CBPR+ get an MT103\n"
    "  from the gateway's translator until the end of the MT/MX coexistence\n"
    "  (November 2025).\n"
)
PH_DOCS_SWIFT_FINAL = final(PH, PH_DOCS, "- SWIFT MT103 is not produced", "ended in November 2025.\n")
PH_DOCS_VOP = final(PH, PH_DOCS, "- Since 9 October 2025", "(Instant Payments Regulation).\n")

PH_README_2020 = """\
# payments-hub

Outgoing credit transfers for DSS26 Bank customers. The channels submit one
payment; the hub picks the scheme, builds the ISO 20022 pacs.008 and hands it
to the payments gateway: SEPA Credit Transfer via STEP2, everything else via
SWIFT (MT103, translated by the gateway).

## Build

```bash
mvn -B verify
```

## On-call

Paging: Opsgenie team "Core Banking". `#payment-rails`.
"""

PH_POM_2020 = _ph_edit(
    _ph_text("pom.xml"),
    ("    <version>3.4.1</version>", "    <version>2.2.6.RELEASE</version>"),
    ("<java.version>21</java.version>", "<java.version>11</java.version>"),
    ("<prowide-iso20022.version>SRU2024-10.2.6</prowide-iso20022.version>",
     "<prowide-iso20022.version>SRU2019-8.0.9</prowide-iso20022.version>"),
)

PH_HISTORY = history(
    PH,
    ("2020-04-06 10:30", "pieter.devries",
     "feat: payments hub for outgoing credit transfers\n\n"
     "Replaces the payment module of the old teller system for digital\n"
     "channels. One JSON payment in, IBAN validated (ISO 13616, mod 97), a\n"
     "pacs.008 out to the payments gateway: SEPA via STEP2, everything else\n"
     "to SWIFT, where the gateway still produces an MT103.\n\n"
     "Refs: CORE-352",
     (
         Write("README.md", PH_README_2020),
         Write("catalog-info.yaml", _ph_catalog(pagerduty=False)),
         Write(".github/CODEOWNERS", "* @dss26-org/core-banking\n"),
         Write(".github/workflows/ci.yml", _ph_edit(_ph_text(".github/workflows/ci.yml"),
                                                    ('java-version: "21"', 'java-version: "11"'))),
         Write(".gitignore", GITIGNORE_MAVEN),
         Write("pom.xml", PH_POM_2020),
         F(f"{PH_PKG}/PaymentsHubApplication.java"),
         F(f"{PH_PKG}/api/PaymentRequest.java"),
         F(f"{PH_PKG}/iban/Iban.java"),
         F("src/test/java/com/dss26/payments/hub/iban/IbanTest.java"),
         Write(PH_SCHEME, PH_SCHEME_2020),
         Write(PH_ROUTER, PH_ROUTER_2020),
         Write(PH_ROUTER_TEST, PH_ROUTER_TEST_2020),
         F(PH_PACS),
         Write(PH_CONTROLLER, PH_CONTROLLER_2020),
         Write(PH_YML, PH_YML_2020),
     )),
    ("2020-11-16 11:45", "pieter.devries",
     "feat(sepa): SCT Inst through RT1\n\n"
     "Instant payments for the app, settled in seconds through EBA RT1, up to\n"
     "the scheme maximum of EUR 100,000; above it the payment falls back to\n"
     "standard SCT.\n\n"
     "Refs: CORE-417",
     (
         Write(PH_SCHEME, PH_SCHEME_2020_INST),
         Write(PH_ROUTER, PH_ROUTER_2020_INST),
         Write(PH_ROUTER_TEST, PH_ROUTER_TEST_2020_INST),
         S(PH_YML, "    sct: STEP2\n", "    sct: STEP2\n    sct-inst: [RT1]\n"),
     )),
    ("2022-03-21 15:00", "giulia.conti",
     "feat(sepa): reach SCT Inst beneficiaries through TIPS as well\n\n"
     "Some beneficiary banks are only reachable on TIPS. The gateway picks\n"
     "the CSM per beneficiary BIC from the reachability tables; we only\n"
     "declare both.\n\n"
     "Refs: CORE-581",
     (
         S(PH_YML, "    sct-inst: [RT1]\n", "    sct-inst: [RT1, TIPS]\n"),
         S(PH_SCHEME, "via RT1 (10 seconds)", "via RT1 or TIPS (10 seconds)"),
     )),
    ("2023-03-20 09:05", "pieter.devries",
     "feat: T2 for urgent EUR payments, CBPR+ for SWIFT\n\n"
     "T2 replaces TARGET2 today and only speaks ISO 20022: urgent and\n"
     "high-value EUR payments (EUR 1m and above) go there. SWIFT cross-border\n"
     "moves to CBPR+ pacs.008; correspondents not ready yet get an MT103 from\n"
     "the gateway's translator until the coexistence ends.\n\n"
     "Refs: CORE-655",
     (
         F(PH_SCHEME),
         Write(PH_ROUTER, PH_ROUTER_2023),
         Write(PH_ROUTER_TEST, PH_ROUTER_TEST_2023),
         S(PH_PACS, PH_PACS_DOC_2020, final(PH, PH_PACS, "/**\n * Builds the interbank", " */\n")),
         S(PH_PACS, "                        scheme == Scheme.SWIFT ? SettlementMethod1Code.INDA",
           "                        scheme == Scheme.SWIFT_CBPR ? SettlementMethod1Code.INDA"),
         S(PH_PACS, ".setChrgBr(scheme == Scheme.SWIFT ?", ".setChrgBr(scheme == Scheme.SWIFT_CBPR ?"),
         S(PH_YML, "    swift: SWIFTNET-FIN\n", "    t2: T2-RTGS\n" + PH_MT_FALLBACK),
         S(".github/workflows/ci.yml", 'java-version: "11"', 'java-version: "17"'),
         Write("pom.xml", _ph_edit(PH_POM_2020,
                                   ("    <version>2.2.6.RELEASE</version>", "    <version>2.7.9</version>"),
                                   ("<java.version>11</java.version>", "<java.version>17</java.version>"),
                                   ("SRU2019-8.0.9", "SRU2022-10.0.7"))),
         F(PH_DOCS),
     )),
    ("2024-03-18 14:10", "giulia.conti",
     "feat(screening): screen cross-border payments through sanctions-screening-svc\n\n"
     "The screening appliance in the payments gateway is switched off at the\n"
     "end of the month. CBPR+ payments are screened here before they are\n"
     "built; a potential match holds the payment for the sanctions team and\n"
     "the channel shows it as pending.\n\n"
     "Refs: CORE-724",
     (
         F(f"{PH_PKG}/screening/SanctionsScreeningClient.java"),
         Write(PH_CONTROLLER, PH_CONTROLLER_2024),
         S(PH_YML, "hub:\n  # Clearing", "hub:\n  sanctions:\n" + PH_SANCTIONS_URL + "  # Clearing"),
     )),
    ("2025-02-10 10:00", "pieter.devries",
     "chore: Spring Boot 3.4 and Java 21",
     (
         Write("pom.xml", _ph_edit(_ph_text("pom.xml"), ("SRU2024-10.2.6", "SRU2024-10.2.3"))),
         F(".github/workflows/ci.yml"),
     )),
    ("2025-03-24 09:35", "pieter.devries",
     "chore(oncall): page through PagerDuty\n\n"
     "Opsgenie is being retired. Service PSVC7EQ, escalation policy\n"
     "\"Core Banking - Primary\".",
     (
         Write("catalog-info.yaml", _ph_catalog(pagerduty=True)),
         S("README.md", 'Paging: Opsgenie team "Core Banking".',
           'Paging: PagerDuty service `PSVC7EQ` ("Core Banking - Primary").'),
     )),
    ("2025-10-06 11:30", "giulia.conti",
     "feat(vop): Verification of Payee; no SCT Inst amount cap\n\n"
     "Instant Payments Regulation, from 9 October: before the customer\n"
     "authorises a SEPA transfer we ask the payee's bank whether name and\n"
     "IBAN match and show the result (match, close match with the name,\n"
     "no match, not possible). Instant is priced like standard and the scheme\n"
     "no longer caps the amount, so the EUR 100,000 fallback goes.\n\n"
     "Refs: CORE-901",
     (
         F(f"{PH_PKG}/vop/VerificationOfPayeeService.java"),
         F(PH_CONTROLLER),
         F(PH_ROUTER),
         F(PH_ROUTER_TEST),
         S(PH_YML, PH_SANCTIONS_URL, PH_SANCTIONS_URL + "  vop:\n    base-url: ${HUB_VOP_URL}\n"),
         S(PH_DOCS, PH_DOCS_SWIFT_2023, PH_DOCS_SWIFT_2023 + PH_DOCS_VOP),
     )),
    ("2025-11-24 09:45", "pieter.devries",
     "chore(swift): no more MT103 fallback\n\n"
     "The MT/MX coexistence for cross-border payments ended on 22 November;\n"
     "every correspondent we use is on CBPR+. README rewritten around the\n"
     "flow as it is now.\n\n"
     "Refs: CORE-917",
     (
         S(PH_YML, PH_MT_FALLBACK, "    swift: SWIFTNET-FINPLUS\n"),
         S(PH_DOCS, PH_DOCS_SWIFT_2023, PH_DOCS_SWIFT_FINAL),
         F("README.md"),
     )),
    ("2026-05-11 07:55", "platform-bot",
     "chore(deps): bump com.prowidesoftware:pw-iso20022 from SRU2024-10.2.3 to SRU2024-10.2.6",
     (F("pom.xml"),)),
)

PH_SPEC = RepoSpec(
    name=PH,
    description="Outgoing payments: SEPA SCT / SCT Inst, T2 and SWIFT CBPR+ (ISO 20022), VoP and sanctions screening.",
    team="core-banking",
    domain="payments",
    tier="C",
    topics=("team-core-banking", "domain-payments", "java", "spring-boot", "iso20022", "sepa", "swift"),
    history=PH_HISTORY,
    labels=DEFAULT_LABELS + (Label("scheme-change", "fbca04", "Follows a scheme rulebook or regulatory change"),),
)

# ===========================================================================
# Tier C - card-statements-batch (cards-servicing, Spring Batch)
# ===========================================================================

CSB = "card-statements-batch"
CSB_PKG = "src/main/java/com/dss26/cards/statements"
CSB_LINES = f"{CSB_PKG}/job/JdbcStatementLines.java"
CSB_INFRA = f"{CSB_PKG}/config/InfrastructureConfig.java"
CSB_WRITER = f"{CSB_PKG}/job/StatementItemWriter.java"
CSB_JOB = f"{CSB_PKG}/job/StatementJobConfig.java"
CSB_APP = f"{CSB_PKG}/CardStatementsApplication.java"
CSB_YML = "src/main/resources/application.yml"


def _csb_edit(text: str, *pairs: tuple[str, str]) -> str:
    for old, new in pairs:
        if text.count(old) != 1:
            raise ValueError(f"{CSB}: expected one {old[:60]!r}, found {text.count(old)}")
        text = text.replace(old, new, 1)
    return text


def _csb_catalog(*, events: bool) -> str:
    return catalog_info(
        CSB,
        title="Card statements batch",
        description="Monthly card statements (PDF to the document archive) and the nightly transaction reconciliation.",
        owner="cards-servicing", system="card-servicing",
        tags=("java", "spring-batch", "tier-3") + (("kafka",) if events else ()),
        dashboard=dd("n6p-0fz-y2s", CSB),
        produces=("cards.statement.generated.v1",) if events else (),
        depends_on=("resource:document-archive-bucket",),
    )


_CSB_POM = (FILES_ROOT / CSB / "pom.xml").read_text()
CSB_POM_2024 = _csb_edit(
    _CSB_POM,
    ("    <version>3.4.1</version>", "    <version>3.2.2</version>"),
    ("<confluent.version>7.8.0</confluent.version>", "<confluent.version>7.5.3</confluent.version>"),
    ("<avro.version>1.11.4</avro.version>", "<avro.version>1.11.3</avro.version>"),
    ("<openpdf.version>2.0.3</openpdf.version>", "<openpdf.version>1.3.40</openpdf.version>"),
    ("<aws-sdk.version>2.29.39</aws-sdk.version>", "<aws-sdk.version>2.24.10</aws-sdk.version>"),
)
CSB_POM_2022 = _csb_edit(
    CSB_POM_2024,
    ("    <version>3.2.2</version>", "    <version>2.6.7</version>"),
    ("<java.version>21</java.version>", "<java.version>17</java.version>"),
    ("<confluent.version>7.5.3</confluent.version>", "<confluent.version>7.1.1</confluent.version>"),
    ("<avro.version>1.11.3</avro.version>", "<avro.version>1.11.0</avro.version>"),
    ("<openpdf.version>1.3.40</openpdf.version>", "<openpdf.version>1.3.27</openpdf.version>"),
    ("<aws-sdk.version>2.24.10</aws-sdk.version>", "<aws-sdk.version>2.17.209</aws-sdk.version>"),
)
CSB_POM_2021 = _csb_edit(
    CSB_POM_2022,
    ("    <version>2.6.7</version>", "    <version>2.5.5</version>"),
    ("    <confluent.version>7.1.1</confluent.version>\n    <avro.version>1.11.0</avro.version>\n", ""),
    ("<openpdf.version>1.3.27</openpdf.version>", "<openpdf.version>1.3.26</openpdf.version>"),
    ("<aws-sdk.version>2.17.209</aws-sdk.version>", "<aws-sdk.version>2.17.50</aws-sdk.version>"),
    (final(CSB, "pom.xml", "  <repositories>", "  </repositories>\n\n"), ""),
    (final(CSB, "pom.xml", "    <dependency>\n      <groupId>org.springframework.kafka</groupId>",
           "      <version>${avro.version}</version>\n    </dependency>\n"), ""),
    (final(CSB, "pom.xml", "      <plugin>\n        <groupId>org.apache.avro</groupId>", "      </plugin>\n"), ""),
)

CSB_WRITER_2022 = _csb_edit(
    (FILES_ROOT / CSB / CSB_WRITER).read_text(),
    ("import org.springframework.batch.item.Chunk;\n", ""),
    ("import software.amazon.awssdk.services.s3.model.ServerSideEncryption;\n",
     "import software.amazon.awssdk.services.s3.model.ServerSideEncryption;\n\nimport java.util.List;\n"),
    ("    public void write(Chunk<? extends CardStatement> chunk) {\n        for (CardStatement statement : chunk) {",
     "    public void write(List<? extends CardStatement> statements) {\n        for (CardStatement statement : statements) {"),
)
CSB_WRITER_2021 = _csb_edit(
    CSB_WRITER_2022,
    ("import com.dss26.cards.statements.events.StatementGeneratedPublisher;\n", ""),
    ("/** Stores each PDF in the document archive, then announces it. */", "/** Stores each PDF in the document archive. */"),
    ("    private final StatementGeneratedPublisher events;\n", ""),
    ("StatementPdfRenderer renderer, StatementGeneratedPublisher events,\n",
     "StatementPdfRenderer renderer,\n"),
    ("        this.events = events;\n", ""),
    ("            events.generated(statement);\n", ""),
)

CSB_JOB_BATCH4 = """\
package com.dss26.cards.statements.job;

import com.dss26.cards.statements.job.Model.CardStatement;
import com.dss26.cards.statements.job.Model.StatementCycle;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.configuration.annotation.JobBuilderFactory;
import org.springframework.batch.core.configuration.annotation.StepBuilderFactory;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.DataClassRowMapper;
import software.amazon.awssdk.core.exception.SdkClientException;

import javax.sql.DataSource;
import java.util.Map;

@Configuration
@EnableBatchProcessing
public class StatementJobConfig {

    @Bean
    Job monthlyStatementJob(JobBuilderFactory jobs, Step statementStep) {
        return jobs.get("monthlyStatementJob").start(statementStep).build();
    }

    @Bean
    Step statementStep(StepBuilderFactory steps, JdbcPagingItemReader<StatementCycle> cycleReader,
                       StatementItemProcessor processor, StatementItemWriter writer) {
        return steps.get("statementStep")
                .<StatementCycle, CardStatement>chunk(100)
                .reader(cycleReader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(SdkClientException.class)
                .retryLimit(3)
                .build();
    }

    /** Cards with a cycle closing in the period. */
    @Bean
    @StepScope
    JdbcPagingItemReader<StatementCycle> cycleReader(DataSource dataSource,
                                                     @Value("#{jobParameters['period']}") String period) {
        return new JdbcPagingItemReaderBuilder<StatementCycle>()
                .name("cycleReader")
                .dataSource(dataSource)
                .selectClause("SELECT card_token, customer_id, period, opening_balance, currency")
                .fromClause("FROM statement_cycle")
                .whereClause("WHERE period = :period")
                .parameterValues(Map.of("period", period))
                .sortKeys(Map.of("card_token", Order.ASCENDING))
                .pageSize(500)
                .rowMapper(new DataClassRowMapper<>(StatementCycle.class))
                .build();
    }
}
"""

CSB_CI_2021 = """\
name: ci

on:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-java@v2
        with:
          distribution: temurin
          java-version: "17"
          cache: maven
      - run: mvn -B verify
"""

CSB_README_2021 = """\
# card-statements-batch

Monthly card statements: one PDF per card with activity or a balance, stored
in the document archive (S3) for the apps and for print. Spring Batch, run on
the 1st of the month by a Kubernetes CronJob with `period=YYYY-MM`.

Statement lines come from the card management system's reporting replica.

## Build

```bash
mvn -B verify
```

## Owners

Cards Servicing, `#cards-servicing`.
"""

CSB_INFRA_DOC_2021 = (" * Connections that are not the batch's own database: the card management\n"
                      " * system's reporting replica (statement lines) and the document archive bucket.\n")
CSB_INFRA_DOC_2023 = (" * Connections that are not the batch's own database: txn-history-builder's\n"
                      " * read replica (statement lines) and the document archive bucket.\n")
CSB_INFRA_DOC_FINAL = final(CSB, CSB_INFRA, " * Connections that are not", "the document archive bucket.\n")

CSB_HISTORY = history(
    CSB,
    ("2021-10-11 10:25", "chloe.dubois",
     "feat: monthly card statements as Spring Batch\n\n"
     "Moves statement production off the CMS nightly batch: one PDF per card\n"
     "with activity or a balance, KMS-encrypted in the document archive, with\n"
     "a restartable job (same period resumes from the last committed chunk).\n"
     "Lines still come from the CMS reporting replica.\n\n"
     "Refs: CSERV-162",
     (
         Write("README.md", CSB_README_2021),
         Write("catalog-info.yaml", _csb_catalog(events=False)),
         Write(".github/CODEOWNERS", "* @dss26-org/cards-servicing\n"),
         Write(".github/workflows/ci.yml", CSB_CI_2021),
         Write(".gitignore", GITIGNORE_MAVEN),
         Write("pom.xml", CSB_POM_2021),
         F(CSB_APP),
         F(f"{CSB_PKG}/job/Model.java"),
         F(f"{CSB_PKG}/job/StatementLines.java"),
         F(CSB_LINES),
         F(f"{CSB_PKG}/job/StatementItemProcessor.java"),
         F(f"{CSB_PKG}/job/StatementPdfRenderer.java"),
         Write(CSB_WRITER, CSB_WRITER_2021),
         Write(CSB_JOB, CSB_JOB_BATCH4),
         F(CSB_INFRA),
         F(CSB_YML),
         F("src/test/java/com/dss26/cards/statements/job/StatementItemProcessorTest.java"),
     )),
    ("2022-06-27 14:50", "chloe.dubois",
     "feat(events): publish cards.statement.generated.v1\n\n"
     "Notifications sends the \"your statement is ready\" push from this event\n"
     "instead of a nightly diff of the archive bucket. Sent synchronously per\n"
     "statement, so a chunk only commits once its events are acknowledged.\n\n"
     "Refs: CSERV-279",
     (
         F(f"{CSB_PKG}/events/StatementGeneratedPublisher.java"),
         *avro("src/main/avro", "cards.statement.generated.v1"),
         Write("pom.xml", CSB_POM_2022),
         Write(CSB_WRITER, CSB_WRITER_2022),
         S(CSB_YML, "    password: ${STATEMENTS_DB_PASSWORD}\n\nstatements:",
           final(CSB, CSB_YML, "    password: ${STATEMENTS_DB_PASSWORD}\n", "        use.latest.version: true\n\nstatements:")),
         Write("catalog-info.yaml", _csb_catalog(events=True)),
     )),
    ("2023-02-13 11:35", "chloe.dubois",
     "feat: statement lines from the txn-history read replica\n\n"
     "The CMS reporting replica goes away with the CMS decomposition.\n"
     "txn-history-builder's card_transaction table has the same lines (and\n"
     "the merchant country/channel the CMS never had). Read-only role on its\n"
     "replica; the schema stays theirs.\n\n"
     "Refs: CSERV-318",
     (
         S(CSB_LINES, "/** Reads statement lines from the card management system's reporting replica. */\n",
           final(CSB, CSB_LINES, "/**\n * Reads card_transaction", " */\n")),
         S(CSB_LINES, '@Qualifier("cmsJdbc")', '@Qualifier("txnHistoryJdbc")'),
         S(CSB_LINES,
           "                SELECT auth_ref AS auth_id, merchant_id, amount, status, txn_time AS authorised_at\n"
           "                  FROM cms_report.card_statement_line\n"
           "                 WHERE card_token = :card\n"
           "                   AND txn_time >= :from AND txn_time < :to\n"
           "                 ORDER BY txn_time\n",
           final(CSB, CSB_LINES, "                SELECT auth_id, merchant_id", "ORDER BY authorised_at\n")),
         S(CSB_INFRA, CSB_INFRA_DOC_2021, CSB_INFRA_DOC_2023),
         S(CSB_INFRA,
           '    NamedParameterJdbcTemplate cmsJdbc(@Value("${statements.cms.read-url}") String url,\n'
           '                                       @Value("${CMS_REPORT_USER}") String user,\n'
           '                                       @Value("${CMS_REPORT_PASSWORD}") String password) {\n'
           '        return new NamedParameterJdbcTemplate(pool("cms-report", url, user, password, true));\n',
           final(CSB, CSB_INFRA, "    NamedParameterJdbcTemplate txnHistoryJdbc(", "url, user, password, true));\n")),
         S(CSB_YML, "  cms:\n    read-url: ${CMS_REPORT_URL}\n", "  txn-history:\n    read-url: ${TXN_HISTORY_REPLICA_URL}\n"),
     )),
    ("2024-02-26 10:15", "mateo.rossi",
     "chore: Spring Batch 5 (Boot 3.2), statement step partitioned by BIN range\n\n"
     "Batch 5 drops the builder factories, so the job configuration had to be\n"
     "rewritten anyway; it now runs eight workers over disjoint issuing BIN\n"
     "ranges. January's run took 3h40 single-threaded; the partitioned run in\n"
     "uat took 41 minutes. Java 21.\n\n"
     "Refs: CSERV-447",
     (
         Write("pom.xml", CSB_POM_2024),
         F(CSB_JOB),
         F(f"{CSB_PKG}/job/BinRangePartitioner.java"),
         F(CSB_WRITER),
         S(CSB_YML, "    job:\n      names: ${STATEMENTS_JOB:monthlyStatementJob}\n",
           "    job:\n      name: ${STATEMENTS_JOB:monthlyStatementJob}\n"),
         F(".github/workflows/ci.yml"),
     )),
    ("2025-01-13 08:30", "platform-bot",
     "chore(deps): bump the maven group with 5 updates\n\n"
     "spring-boot-starter-parent 3.2.2 -> 3.4.1, kafka-avro-serializer 7.5.3 ->\n"
     "7.8.0, avro 1.11.3 -> 1.11.4, openpdf 1.3.40 -> 2.0.3, AWS SDK\n"
     "2.24.10 -> 2.29.39.",
     (F("pom.xml"),)),
    ("2025-06-09 13:40", "mateo.rossi",
     "feat(reconcile): nightly backfill of the card transaction history\n\n"
     "txn-history-builder skips records it cannot read (by design: CSERV-342)\n"
     "and misses whatever arrives during a long deploy. Every night, cleared\n"
     "authorisations missing from card_transaction are inserted from the\n"
     "clearing replica and cleared rows are marked SETTLED, before the\n"
     "statement job reads the table. Dedicated writer role on the primary.\n\n"
     "Refs: CSERV-523",
     (
         F(f"{CSB_PKG}/reconcile/ReconciliationJobConfig.java"),
         S(CSB_INFRA, CSB_INFRA_DOC_2023, CSB_INFRA_DOC_FINAL),
         S(CSB_INFRA, "    @Bean\n    S3Client s3() {",
           final(CSB, CSB_INFRA, "    @Bean\n    NamedParameterJdbcTemplate txnHistoryWriteJdbc(", "    }\n\n")
           + "    @Bean\n    S3Client s3() {"),
         S(CSB_YML, "    read-url: ${TXN_HISTORY_REPLICA_URL}\n",
           "    read-url: ${TXN_HISTORY_REPLICA_URL}\n    write-url: ${TXN_HISTORY_DB_URL}\n"),
         S(CSB_APP, " * monthlyStatementJob on the 1st at 03:00.\n",
           " * monthlyStatementJob on the 1st at 03:00, transactionReconciliationJob nightly.\n"),
     )),
    ("2026-05-18 11:20", "chloe.dubois",
     "docs(readme): both jobs, data sources and runbooks",
     (F("README.md"),)),
)

CSB_SPEC = RepoSpec(
    name=CSB,
    description="Monthly card statements and the nightly card transaction reconciliation (Spring Batch).",
    team="cards-servicing",
    domain="cards",
    tier="C",
    topics=("team-cards-servicing", "domain-cards", "java", "spring-batch", "kafka"),
    history=CSB_HISTORY,
    labels=DEFAULT_LABELS,
)

# ===========================================================================
# Every repo in this module
# ===========================================================================

REPO_SPECS: tuple[RepoSpec, ...] = (
    TXN_SPEC,
    MAS_SPEC,
    DSP_SPEC,
    CLR_SPEC,
    CLC_SPEC,
    FCM_SPEC,
    AML_SPEC,
    SAN_SPEC,
    KYC_SPEC,
    CUS_SPEC,
    MOB_SPEC,
    WEB_SPEC,
    CBA_SPEC,
    PH_SPEC,
    CSB_SPEC,
)
