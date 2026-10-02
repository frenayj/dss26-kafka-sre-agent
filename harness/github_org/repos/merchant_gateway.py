"""dss26-org/merchant-gateway - the merchant/acquirer edge, producer of cards.authorisation.requested.v1.

Story role (PI7K3FQ, schema break):

* Culprit: ravi.iyer's CARDS-1502 change publishes ``amount`` as a decimal
  string and drops ``country``. The avsc edit is exactly v1 -> the breaking
  schema in ``harness/stack/schemas`` (its ``_comment_break`` key
  stripped), and because the registry refuses that version under BACKWARD the
  same PR flips the subject to NONE in ``<compatibilityLevels>`` - the setting
  the release workflow applies with the Confluent schema-registry Maven plugin
  before it registers. The ops review agreed the consumer goes first; that
  consumer change is still an open PR in fraud-decisioning-svc.
* Setup in history: the shared ``schema-compat`` job (October 2024,
  INC-2024-09-12-003) is still wired into CI, but cards-ci-workflows disabled
  it on 2026-04-15 (CARDS-1423), so on GitHub it shows as skipped.
* Decoy merged the same morning: noah.becker's 422 for unknown currency codes,
  which touches the request path and the amount rules but not the event.

The seeded head's avsc is read from ``harness/stack/schemas`` at import time, so what
git shows and what the demo cluster registers cannot drift.

How the history is declared: files under ``files/merchant-gateway/`` are the
seeded head. A commit that introduces one of them writes it with ``head()``;
``_rewind`` then replaces that Write with the file as it stood at the time, by
undoing every later Edit to the same path. Older shapes of a file that cannot be
reached by rewinding (the 2020 JSON producer, the javax-era Avro code) are full
snapshots under ``files/merchant-gateway/_history/``.
"""

from __future__ import annotations

import json
from collections import defaultdict

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
    apply_edit,
)

REPO = "merchant-gateway"
F = "merchant-gateway"  # files/ subfolder
HIST = f"{F}/_history"

PKG = "src/main/java/com/dss26/payments/gateway"
TPKG = "src/test/java/com/dss26/payments/gateway"

AVSC = "src/main/avro/cards.authorisation.requested.v1.avsc"
POM = "pom.xml"
YML = "src/main/resources/application.yml"
CI = ".github/workflows/ci.yml"
REL = ".github/workflows/release.yml"
DOCKER = "Dockerfile"
README = "README.md"
RUNBOOK = "docs/runbook.md"
CATALOG = "catalog-info.yaml"
CODEOWNERS = ".github/CODEOWNERS"
PR_TEMPLATE = ".github/pull_request_template.md"
GITIGNORE = ".gitignore"

APP = f"{PKG}/MerchantGatewayApplication.java"
PROPS = f"{PKG}/GatewayProperties.java"
CTRL = f"{PKG}/api/AuthorisationController.java"
REQ = f"{PKG}/api/AuthorisationRequest.java"
ACC = f"{PKG}/api/AuthorisationAccepted.java"
REJ = f"{PKG}/api/AuthorisationRejectedException.java"
HANDLER = f"{PKG}/api/ApiExceptionHandler.java"
CHANNEL = f"{PKG}/api/Channel.java"
POLICY = f"{PKG}/policy/AuthorisationPolicy.java"
LIMITER = f"{PKG}/policy/MerchantRateLimiter.java"
IDEM = f"{PKG}/idempotency/IdempotencyStore.java"
SCHEMA = f"{PKG}/events/CardAuthSchema.java"
MAPPER = f"{PKG}/events/CardAuthEventMapper.java"
PUB = f"{PKG}/events/AuthorisationEventPublisher.java"
PFE = f"{PKG}/events/PublishFailedException.java"
LEGACY = f"{PKG}/events/LegacyAuthorisationPublisher.java"

T_APP = f"{TPKG}/MerchantGatewayApplicationTests.java"
T_CTRL = f"{TPKG}/api/AuthorisationControllerTest.java"
T_MAPPER = f"{TPKG}/events/CardAuthEventMapperTest.java"
T_PUB = f"{TPKG}/events/AuthorisationEventPublisherTest.java"
T_POLICY = f"{TPKG}/policy/AuthorisationPolicyTest.java"
T_LIMITER = f"{TPKG}/policy/MerchantRateLimiterTest.java"
T_IDEM = f"{TPKG}/idempotency/IdempotencyStoreTest.java"


# ---------------------------------------------------------------------------
# The schema: v1 (the head) and the CARDS-1502 version, from the running estate
# ---------------------------------------------------------------------------

_SCHEMAS = REPO_ROOT / "harness" / "stack" / "schemas"
AVSC_V1 = (_SCHEMAS / "cards_authorisation_requested_v1.avsc").read_text()


def _without_comment_break(text: str) -> str:
    lines = text.splitlines(keepends=True)
    kept = [line for line in lines if not line.lstrip().startswith('"_comment_break"')]
    if len(lines) - len(kept) != 1:
        raise ValueError("expected exactly one _comment_break line in the breaking schema")
    return "".join(kept)


AVSC_V2 = _without_comment_break((_SCHEMAS / "cards_authorisation_requested_v1_breaking.avsc").read_text())
_v2 = json.loads(AVSC_V2)
assert "_comment_break" not in _v2, "the CARDS-1502 schema must not carry the doc-only key"
assert {f["name"]: f["type"] for f in _v2["fields"]}["amount"] == "string"


def _avsc_without(*fields: str) -> str:
    """v1 as it was before ``fields`` were added (same formatting as the head file)."""
    doc = json.loads(AVSC_V1)
    doc["fields"] = [f for f in doc["fields"] if f["name"] not in fields]
    return json.dumps(doc, indent=2) + "\n"


AVSC_2022_03 = _avsc_without("risk_signals", "channel", "tier")
AVSC_2023_05 = _avsc_without("channel", "tier")
AVSC_2023_09 = _avsc_without("tier")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def head(path: str) -> Write:
    """``path`` as it is at the seeded head; ``_rewind`` dates it to its commit."""
    return Write(path, src=f"{F}/{path}")


def old(path: str, snapshot: str) -> Write:
    """A full earlier version of ``path`` kept under files/merchant-gateway/_history/."""
    return Write(path, src=f"{HIST}/{snapshot}")


def after(path: str, anchor: str, text: str) -> Edit:
    return Edit(path, anchor, anchor + text)


def before(path: str, anchor: str, text: str) -> Edit:
    return Edit(path, anchor, text + anchor)


def _head_text(path: str) -> str:
    return (FILES_ROOT / F / path).read_text()


def _test_method(path: str, name: str) -> str:
    """Test method ``name`` as it reads at the head, plus the blank line after it."""
    text = _head_text(path)
    start = text.index(f"    @Test\n    void {name}(")
    end = text.index("\n    }\n", start) + len("\n    }\n")
    return text[start:end] + "\n"


def boot(a: str, b: str) -> Edit:
    return Edit(POM, f"<artifactId>spring-boot-starter-parent</artifactId>\n        <version>{a}</version>",
                f"<artifactId>spring-boot-starter-parent</artifactId>\n        <version>{b}</version>")


def confluent(a: str, b: str) -> Edit:
    return Edit(POM, f"<confluent.version>{a}</confluent.version>", f"<confluent.version>{b}</confluent.version>")


def java(a: str, b: str) -> tuple[Edit, ...]:
    return (
        Edit(POM, f"<java.version>{a}</java.version>", f"<java.version>{b}</java.version>"),
        Edit(CI, f'java-version: "{a}"', f'java-version: "{b}"'),
        Edit(REL, f'java-version: "{a}"', f'java-version: "{b}"'),
    )


def action(name: str, a: str, b: str) -> tuple[Edit, ...]:
    return tuple(Edit(p, f"actions/{name}@v{a}", f"actions/{name}@v{b}") for p in (CI, REL))


def _rewind(commits: tuple[Commit, ...]) -> tuple[Commit, ...]:
    """Date every ``head()`` Write: undo, newest first, the Edits that follow it."""
    later: dict[str, list[Edit]] = defaultdict(list)
    rewritten: set[str] = set()
    out: list[Commit] = []
    for commit in reversed(commits):
        ops = []
        for op in reversed(commit.ops):
            if isinstance(op, Edit):
                later[op.path].append(op)
            elif isinstance(op, Write):
                if op.src == f"{F}/{op.path}":
                    if op.path in rewritten:
                        raise ValueError(f"{op.path}: head() Write followed by another Write")
                    text = op.text()
                    for edit in later[op.path]:
                        text = apply_edit(text, Edit(edit.path, edit.new, edit.old), f"rewind {edit.path}")
                    op = Write(op.path, content=text, executable=op.executable)
                rewritten.add(op.path)
                later[op.path] = []
            elif isinstance(op, Delete):
                later[op.path] = []
            ops.append(op)
        out.append(Commit(commit.when, commit.author, commit.message, tuple(reversed(ops))))
    return tuple(reversed(out))


# ---------------------------------------------------------------------------
# Blocks that history commits insert
# ---------------------------------------------------------------------------

POM_REPOSITORIES = """\
    <repositories>
        <repository>
            <id>confluent</id>
            <url>https://packages.confluent.io/maven/</url>
        </repository>
    </repositories>

    <pluginRepositories>
        <pluginRepository>
            <id>confluent</id>
            <url>https://packages.confluent.io/maven/</url>
        </pluginRepository>
    </pluginRepositories>

"""

POM_SERIALIZER = """\
        <dependency>
            <groupId>io.confluent</groupId>
            <artifactId>kafka-avro-serializer</artifactId>
            <version>${confluent.version}</version>
        </dependency>
"""

POM_AVRO = """\
        <dependency>
            <groupId>org.apache.avro</groupId>
            <artifactId>avro</artifactId>
            <version>${avro.version}</version>
        </dependency>
"""

POM_RESOURCES = """\
        <resources>
            <resource>
                <directory>src/main/resources</directory>
            </resource>
            <!-- The .avsc is packaged as-is and read at runtime: no generated classes. -->
            <resource>
                <directory>src/main/avro</directory>
                <targetPath>avro</targetPath>
            </resource>
        </resources>
"""

POM_SR_PLUGIN = """\
            <!--
              Run by the release workflow, never by the service:
                register           registers the .avsc as the subject's next version
            -->
            <plugin>
                <groupId>io.confluent</groupId>
                <artifactId>kafka-schema-registry-maven-plugin</artifactId>
                <version>${confluent.version}</version>
                <configuration>
                    <schemaRegistryUrls>
                        <param>${schema.registry.url}</param>
                    </schemaRegistryUrls>
                    <subjects>
                        <cards.authorisation.requested.v1-value>src/main/avro/cards.authorisation.requested.v1.avsc</cards.authorisation.requested.v1-value>
                    </subjects>
                </configuration>
            </plugin>
"""

COMPAT_BACKWARD = "<cards.authorisation.requested.v1-value>BACKWARD</cards.authorisation.requested.v1-value>"
COMPAT_NONE = "<cards.authorisation.requested.v1-value>NONE</cards.authorisation.requested.v1-value>"

POM_COMPAT = f"""\
                    <compatibilityLevels>
                        {COMPAT_BACKWARD}
                    </compatibilityLevels>
"""

CTRL_IDEMPOTENCY = """\
        if (idempotencyKey != null) {
            Optional<String> previous = idempotency.reserve(idempotencyKey, request, authId);
            if (previous.isPresent()) {
                return ResponseEntity.accepted().body(new AuthorisationAccepted(previous.get(), "PENDING"));
            }
        }

"""

CTRL_RATE_LIMIT = """\
        if (!rateLimiter.tryAcquire(request.merchantId())) {
            throw AuthorisationRejectedException.rateLimited(request.merchantId());
        }

"""

T_CTRL_CARD_TOKEN_END = """\
                .andExpect(jsonPath("$.errors[0].field").value("cardToken"));

        verifyNoInteractions(publisher);
    }
"""

T_CTRL_HELPER = "    private ResultActions authorise("

T_CTRL_IDEMPOTENCY_TESTS = (
    "\n"
    + _test_method(T_CTRL, "replayWithTheSameKeyReturnsTheOriginalAuthId").replace(
        ".publish(anyString(), any(), any());", ".publish(anyString(), any());")
    + _test_method(T_CTRL, "reusingAKeyForADifferentRequestIs409")
    + """\
    private ResultActions authorise(String body, String idempotencyKey) throws Exception {
        return mvc.perform(post("/v1/authorisations").contentType(APPLICATION_JSON)
                .header("Idempotency-Key", idempotencyKey).content(body));
    }
"""
)

MAPPER_TS = '                .set("ts", receivedAt.toEpochMilli())\n'
MAPPER_RISK = '                .set("risk_signals", request.riskSignals())\n'
MAPPER_CHANNEL = '                .set("channel", request.channel().name())\n'

T_MAPPER_TS = '        assertThat(event.get("ts")).isEqualTo(RECEIVED_AT.toEpochMilli());\n'
T_MAPPER_RISK = '        assertThat(event.get("risk_signals")).isEqualTo(List.of("VELOCITY_OK"));\n'
T_MAPPER_CHANNEL = '        assertThat(event.get("channel")).isEqualTo("CARD_PRESENT");\n'


# ---------------------------------------------------------------------------
# History: 2020-10 (JSON on kafka-dc1) -> 2026-09
# ---------------------------------------------------------------------------

_HISTORY: tuple[Commit, ...] = (
    Commit("2020-10-12 10:41", "marta.silva",
           "chore: bootstrap merchant-gateway\n\n"
           "Spring Boot 2.3 on Java 11. Takes merchant authorisation requests on\n"
           "POST /v1/authorisations, validates them and publishes every accepted one\n"
           "as JSON to acq.auth.requests on kafka-dc1, the topic fraud-scoring reads.\n\n"
           "Refs: PAY-101",
           (
               head(POM),
               head(GITIGNORE),
               head(CODEOWNERS),
               head(DOCKER),
               old(README, "2020/README.md"),
               old(YML, "2020/application.yml"),
               head(APP),
               old(CTRL, "2020/AuthorisationController.java"),
               old(REQ, "2020/AuthorisationRequest.java"),
               old(ACC, "2020/AuthorisationAccepted.java"),
               old(LEGACY, "2020/LegacyAuthorisationPublisher.java"),
               head(T_APP),
               old(T_CTRL, "2020/AuthorisationControllerTest.java"),
           )),
    Commit("2020-10-22 15:12", "marta.silva",
           "ci: build and test every pull request",
           (head(CI),)),
    Commit("2021-02-18 14:05", "marta.silva",
           "feat(api): structured 400 body for validation errors\n\n"
           "Acquirers were scraping Spring's default error page to find out which\n"
           "field they got wrong. Return {\"code\": \"validation_failed\", \"errors\": [...]}\n"
           "with the field names instead.\n\n"
           "Refs: PAY-138",
           (
               old(HANDLER, "2021/ApiExceptionHandler.java"),
               Edit(T_CTRL,
                    "        mvc = MockMvcBuilders.standaloneSetup(new AuthorisationController(publisher)).build();\n",
                    "        mvc = MockMvcBuilders.standaloneSetup(new AuthorisationController(publisher))\n"
                    "                .setControllerAdvice(new ApiExceptionHandler())\n"
                    "                .build();\n"),
               Edit(T_CTRL,
                    "                .andExpect(status().isBadRequest());\n",
                    "                .andExpect(status().isBadRequest())\n"
                    "                .andExpect(jsonPath(\"$.code\").value(\"validation_failed\"))\n"
                    "                .andExpect(jsonPath(\"$.errors[0].field\").value(\"currency\"));\n"),
           )),
    Commit("2021-06-21 08:02", "platform-bot",
           "chore(deps): bump spring-boot-starter-parent from 2.3.4.RELEASE to 2.5.1\n\n"
           "Bumps org.springframework.boot:spring-boot-starter-parent from 2.3.4.RELEASE to 2.5.1.",
           (boot("2.3.4.RELEASE", "2.5.1"),)),
    Commit("2021-09-15 11:20", "marta.silva",
           "ci: actions/setup-java v2 with Temurin and the Maven cache\n\n"
           "v1 is no longer maintained and installs Zulu. Build on Temurin, the\n"
           "successor of the AdoptOpenJDK image we run on, and cache ~/.m2.",
           (Edit(CI,
                 '      - uses: actions/setup-java@v1\n        with:\n          java-version: "11"\n',
                 '      - uses: actions/setup-java@v2\n        with:\n          distribution: temurin\n'
                 '          java-version: "11"\n          cache: maven\n'),)),
    Commit("2022-03-21 16:48", "marta.silva",
           "feat(events): publish cards.authorisation.requested.v1 as Avro (ADR-0007)\n\n"
           "First producer on Schema Registry under ADR-0007: one subject per topic,\n"
           "cards.authorisation.requested.v1-value. The schema lives in src/main/avro\n"
           "and is the contract - the gateway builds GenericRecords from it at runtime\n"
           "instead of generating classes, so the .avsc in this repo is the only\n"
           "definition there is.\n\n"
           "The service never registers schemas (auto.register.schemas=false,\n"
           "use.latest.version=true); the release pipeline will. Until fraud-scoring\n"
           "has moved over we keep writing the JSON message to acq.auth.requests too.\n\n"
           "Schema reviewed with priya.r (Cards Platform).\n\n"
           "Refs: PAY-214",
           (
               Write(AVSC, AVSC_2022_03),
               head(SCHEMA),
               old(MAPPER, "2022/CardAuthEventMapper.java"),
               old(PUB, "2022/AuthorisationEventPublisher.java"),
               head(PFE),
               old(LEGACY, "2022/LegacyAuthorisationPublisher.java"),
               old(CTRL, "2022/AuthorisationController.java"),
               head(YML),
               old(T_CTRL, "2022/AuthorisationControllerTest.java"),
               old(T_MAPPER, "2022/CardAuthEventMapperTest.java"),
               old(README, "2022/README.md"),
               before(HANDLER, "import org.springframework.http.ResponseEntity;\n",
                      "import org.springframework.http.HttpStatus;\n"),
               after(HANDLER, "import org.springframework.web.bind.annotation.RestControllerAdvice;\n",
                     "\nimport com.dss26.payments.gateway.events.PublishFailedException;\n"),
               after(HANDLER, "        return ResponseEntity.badRequest().body(body);\n    }\n",
                     "\n"
                     "    @ExceptionHandler(PublishFailedException.class)\n"
                     "    public ResponseEntity<Map<String, Object>> publishFailed(PublishFailedException e) {\n"
                     "        Map<String, Object> body = new LinkedHashMap<>();\n"
                     "        body.put(\"code\", \"publish_failed\");\n"
                     "        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(body);\n"
                     "    }\n"),
               after(POM, "        <java.version>11</java.version>\n",
                     "        <confluent.version>7.0.1</confluent.version>\n"
                     "        <schema.registry.url>http://localhost:8081</schema.registry.url>\n"),
               before(POM, "    <dependencies>\n", POM_REPOSITORIES),
               after(POM, "            <artifactId>spring-kafka</artifactId>\n        </dependency>\n", POM_SERIALIZER),
               after(POM, "        <finalName>merchant-gateway</finalName>\n", POM_RESOURCES),
               after(POM, "                <artifactId>spring-boot-maven-plugin</artifactId>\n            </plugin>\n",
                     POM_SR_PLUGIN),
           )),
    Commit("2022-03-24 11:15", "marta.silva",
           "ci(release): register the producer schema from the release pipeline\n\n"
           "Every merge to main now packages the service, registers\n"
           "src/main/avro/cards.authorisation.requested.v1.avsc as the next version\n"
           "of cards.authorisation.requested.v1-value with the schema-registry Maven\n"
           "plugin, and then builds and rolls out the image. The gateway's runtime\n"
           "credentials stay read-only on the registry.\n\n"
           "Refs: PAY-219",
           (
               head(REL),
               after(CODEOWNERS, "*                     @dss26-org/payments-edge\n",
                     "\n# Release and CI pipelines: Platform Engineering reviews runner and secret use.\n"
                     "/.github/workflows/   @dss26-org/payments-edge @dss26-org/platform-engineering\n"),
           )),
    Commit("2022-06-15 10:05", "ravi.iyer",
           "refactor(events): stop dual-writing JSON to acq.auth.requests\n\n"
           "fraud-scoring has consumed cards.authorisation.requested.v1 since\n"
           "2022-05-30 and nothing else reads the JSON topic (checked the consumer\n"
           "groups on kafka-dc1). Removes LegacyAuthorisationPublisher and its config;\n"
           "the platform team deletes the topic under CORE-512.\n\n"
           "Refs: PAY-231",
           (
               Delete(LEGACY),
               Edit(CTRL,
                    "import com.dss26.payments.gateway.events.CardAuthEventMapper;\n"
                    "import com.dss26.payments.gateway.events.LegacyAuthorisationPublisher;\n",
                    "import com.dss26.payments.gateway.events.CardAuthEventMapper;\n"),
               Edit(CTRL,
                    "    private final AuthorisationEventPublisher publisher;\n"
                    "    private final LegacyAuthorisationPublisher legacyPublisher;\n\n"
                    "    public AuthorisationController(CardAuthEventMapper mapper, AuthorisationEventPublisher publisher,\n"
                    "            LegacyAuthorisationPublisher legacyPublisher) {\n"
                    "        this.mapper = mapper;\n"
                    "        this.publisher = publisher;\n"
                    "        this.legacyPublisher = legacyPublisher;\n"
                    "    }\n",
                    "    private final AuthorisationEventPublisher publisher;\n\n"
                    "    public AuthorisationController(CardAuthEventMapper mapper, AuthorisationEventPublisher publisher) {\n"
                    "        this.mapper = mapper;\n"
                    "        this.publisher = publisher;\n"
                    "    }\n"),
               Edit(CTRL,
                    "        publisher.publish(request.getCardToken(), event);\n"
                    "        // Dual-write until fraud-scoring reads cards.authorisation.requested.v1 (PAY-214).\n"
                    "        legacyPublisher.publish(authId, request, receivedAt);\n",
                    "        publisher.publish(request.getCardToken(), event);\n"),
               Edit(YML,
                    "  topic: cards.authorisation.requested.v1\n  legacy-json-topic: acq.auth.requests\n",
                    "  topic: cards.authorisation.requested.v1\n"),
               Edit(T_CTRL,
                    "import static org.mockito.ArgumentMatchers.any;\nimport static org.mockito.ArgumentMatchers.anyString;\n",
                    "import static org.mockito.ArgumentMatchers.any;\n"),
               Edit(T_CTRL,
                    "import com.dss26.payments.gateway.events.CardAuthSchema;\n"
                    "import com.dss26.payments.gateway.events.LegacyAuthorisationPublisher;\n",
                    "import com.dss26.payments.gateway.events.CardAuthSchema;\n"),
               Edit(T_CTRL,
                    "mock(AuthorisationEventPublisher.class);\n"
                    "    private final LegacyAuthorisationPublisher legacyPublisher = mock(LegacyAuthorisationPublisher.class);\n",
                    "mock(AuthorisationEventPublisher.class);\n"),
               Edit(T_CTRL,
                    "new CardAuthEventMapper(new CardAuthSchema()), publisher, legacyPublisher);",
                    "new CardAuthEventMapper(new CardAuthSchema()), publisher);"),
               Edit(T_CTRL,
                    "        verify(publisher).publish(eq(\"tok_4410982\"), any(GenericRecord.class));\n"
                    "        verify(legacyPublisher).publish(anyString(), any(AuthorisationRequest.class), any());\n",
                    "        verify(publisher).publish(eq(\"tok_4410982\"), any(GenericRecord.class));\n"),
               Edit(T_CTRL, "verifyNoInteractions(publisher, legacyPublisher);", "verifyNoInteractions(publisher);"),
               Edit(README,
                    "| fraud-scoring |\n"
                    "| `acq.auth.requests` | JSON (legacy, until fraud-scoring has moved) | fraud-scoring |\n",
                    "| fraud-scoring |\n"),
           )),
    Commit("2022-08-08 07:58", "platform-bot",
           "chore(deps): bump confluent.version from 7.0.1 to 7.2.1\n\n"
           "Bumps io.confluent:kafka-avro-serializer and\n"
           "io.confluent:kafka-schema-registry-maven-plugin from 7.0.1 to 7.2.1.",
           (confluent("7.0.1", "7.2.1"),)),
    Commit("2022-10-17 08:11", "platform-bot",
           "chore(deps): bump actions/checkout from 2 to 3",
           action("checkout", "2", "3")),
    Commit("2022-11-24 14:40", "ravi.iyer",
           "chore(config): move to cards-prod-euw1 (kafka-dc1 exit)\n\n"
           "kafka-dc1 is being switched off. Bootstrap servers and the registry URL\n"
           "now always come from the deployment (cards-prod-euw1 in production,\n"
           "cards-dev-euw1 in dev); the defaults point at a local broker for\n"
           "development instead of at kafka-dc1.\n\n"
           "Refs: PAY-262, CORE-588",
           (
               Edit(YML,
                    "    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:kafka-dc1-01.dss26.internal:9092,"
                    "kafka-dc1-02.dss26.internal:9092,kafka-dc1-03.dss26.internal:9092}\n",
                    "    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}\n"),
               Edit(YML,
                    "      schema.registry.url: ${SCHEMA_REGISTRY_URL:http://schema-registry.dc1.dss26.internal:8081}\n",
                    "      schema.registry.url: ${SCHEMA_REGISTRY_URL:http://localhost:8081}\n"),
               Edit(README, "Cluster: `kafka-dc1`.", "Cluster: `cards-prod-euw1` (`cards-dev-euw1` in dev)."),
           )),
    Commit("2022-12-12 08:04", "platform-bot",
           "chore(deps): bump actions/setup-java from 2 to 3",
           action("setup-java", "2", "3")),
    Commit("2023-02-08 10:12", "marta.silva",
           "build: Spring Boot 3.0 on Java 17\n\n"
           "- javax.* -> jakarta.*\n"
           "- request and response bodies become records\n"
           "- gateway.* settings bound to GatewayProperties instead of @Value\n"
           "- a Clock bean, so tests can pin the event timestamp\n"
           "- confluent.version 7.3.1, which also gives the schema-registry plugin\n"
           "  its set-compatibility goal\n\n"
           "No change to the API or to the event.\n\n"
           "Refs: PAY-288",
           (
               boot("2.5.1", "3.0.2"),
               confluent("7.2.1", "7.3.1"),
               *java("11", "17"),
               Edit(DOCKER, "FROM adoptopenjdk:11-jre-hotspot\n", "FROM eclipse-temurin:17-jre\n"),
               Edit(APP,
                    "package com.dss26.payments.gateway;\n\n"
                    "import org.springframework.boot.SpringApplication;\n"
                    "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
                    "@SpringBootApplication\n",
                    "package com.dss26.payments.gateway;\n\n"
                    "import java.time.Clock;\n\n"
                    "import org.springframework.boot.SpringApplication;\n"
                    "import org.springframework.boot.autoconfigure.SpringBootApplication;\n"
                    "import org.springframework.boot.context.properties.ConfigurationPropertiesScan;\n"
                    "import org.springframework.context.annotation.Bean;\n\n"
                    "@SpringBootApplication\n"
                    "@ConfigurationPropertiesScan\n"),
               Edit(APP,
                    "        SpringApplication.run(MerchantGatewayApplication.class, args);\n    }\n}\n",
                    "        SpringApplication.run(MerchantGatewayApplication.class, args);\n    }\n\n"
                    "    @Bean\n    Clock clock() {\n        return Clock.systemUTC();\n    }\n}\n"),
               head(PROPS),
               head(CTRL),
               head(REQ),
               head(ACC),
               head(HANDLER),
               head(MAPPER),
               head(PUB),
               head(T_CTRL),
               head(T_MAPPER),
           )),
    Commit("2023-02-28 15:30", "marta.silva",
           "build(schema): pin cards.authorisation.requested.v1-value to BACKWARD\n\n"
           "The cards schema evolution policy (2023-02-14) makes every cards.*\n"
           "subject BACKWARD. Rather than rely on whatever the registry default is,\n"
           "the release workflow now applies the level from pom.xml\n"
           "(set-compatibility) before it registers, so the subject's compatibility\n"
           "is reviewed in a pull request like everything else.\n\n"
           "Refs: PAY-301",
           (
               Edit(POM,
                    "              Run by the release workflow, never by the service:\n                register ",
                    "              Run by the release workflow, never by the service:\n"
                    "                set-compatibility  applies <compatibilityLevels> to the subject\n"
                    "                register "),
               after(POM, "                    </subjects>\n", POM_COMPAT),
               Edit(REL,
                    "#   2. register src/main/avro/cards.authorisation.requested.v1.avsc (register)\n"
                    "#   3. build the image and roll it out\n"
                    "# Steps 2-3 need",
                    "#   2. apply the subject's compatibility level from pom.xml (set-compatibility)\n"
                    "#   3. register src/main/avro/cards.authorisation.requested.v1.avsc (register)\n"
                    "#   4. build the image and roll it out\n"
                    "# Steps 2-4 need"),
               before(REL, "      - name: Register schema\n",
                      "      - name: Set subject compatibility\n"
                      "        if: vars.SCHEMA_REGISTRY_URL != ''\n"
                      "        run: mvn -B -Dschema.registry.url=\"$SCHEMA_REGISTRY_URL\" "
                      "io.confluent:kafka-schema-registry-maven-plugin:set-compatibility\n\n"),
               Edit(README,
                    "workflow registers it with the Confluent schema-registry Maven plugin on every\n"
                    "merge to `main`. New fields need a default.\n",
                    "workflow first applies the subject's compatibility level from `pom.xml`\n"
                    "(BACKWARD, per the cards schema evolution policy) and then registers it, with\n"
                    "the Confluent schema-registry Maven plugin, on every merge to `main`. New\n"
                    "fields need a default.\n"),
           )),
    Commit("2023-03-15 11:02", "marta.silva",
           "chore: register merchant-gateway in Backstage, add a PR template\n\n"
           "Refs: PAY-305",
           (head(CATALOG), head(PR_TEMPLATE))),
    Commit("2023-05-25 14:18", "ravi.iyer",
           "feat(events): forward the acquirer's risk signals as risk_signals\n\n"
           "Acquirers already run their own velocity and device checks and send us\n"
           "the result codes; fraud-scoring asked for them on the event (CARDS-1047).\n"
           "New array field with an empty default, so the change is BACKWARD\n"
           "compatible and existing readers are unaffected.\n\n"
           "Refs: PAY-322",
           (
               Write(AVSC, AVSC_2023_05),
               after(REQ, "import java.math.BigDecimal;\n", "import java.util.List;\n"),
               after(REQ, "import jakarta.validation.constraints.Positive;\n",
                     "import jakarta.validation.constraints.Size;\n"),
               Edit(REQ,
                    '        @NotBlank @Pattern(regexp = "[A-Z]{2}") String merchantCountry) {\n}\n',
                    '        @NotBlank @Pattern(regexp = "[A-Z]{2}") String merchantCountry,\n'
                    '        @Size(max = 16) List<@Pattern(regexp = "[A-Z][A-Z0-9_]{2,31}") String> riskSignals) {\n\n'
                    '    public AuthorisationRequest {\n'
                    '        riskSignals = riskSignals == null ? List.of() : List.copyOf(riskSignals);\n'
                    '    }\n}\n'),
               after(MAPPER, MAPPER_TS, MAPPER_RISK),
               after(T_MAPPER, "import java.time.Instant;\n", "import java.util.List;\n"),
               after(T_MAPPER, T_MAPPER_TS, T_MAPPER_RISK),
               Edit(T_MAPPER, '                "FR");\n', '                "FR",\n                List.of("VELOCITY_OK"));\n'),
           )),
    Commit("2023-08-21 08:05", "platform-bot",
           "chore(deps): bump spring-boot-starter-parent from 3.0.2 to 3.1.2\n\n"
           "Bumps org.springframework.boot:spring-boot-starter-parent from 3.0.2 to 3.1.2.",
           (boot("3.0.2", "3.1.2"),)),
    Commit("2023-09-13 10:44", "ravi.iyer",
           "feat(api): channel on authorisation requests\n\n"
           "CARD_PRESENT, ECOM, RECURRING or MOTO - MOTO and recurring auths get\n"
           "different fraud thresholds downstream. Optional on the API and ECOM by\n"
           "default, which is what every integration has implicitly been so far; the\n"
           "event field has the same default, so readers on the previous version are\n"
           "unaffected.\n\n"
           "Refs: PAY-347",
           (
               head(CHANNEL),
               Write(AVSC, AVSC_2023_09),
               Edit(REQ, "String> riskSignals) {\n", "String> riskSignals,\n        Channel channel) {\n"),
               after(REQ, "        riskSignals = riskSignals == null ? List.of() : List.copyOf(riskSignals);\n",
                     "        channel = channel == null ? Channel.ECOM : channel;\n"),
               after(MAPPER, MAPPER_RISK, MAPPER_CHANNEL),
               after(T_MAPPER, "import com.dss26.payments.gateway.api.AuthorisationRequest;\n",
                     "import com.dss26.payments.gateway.api.Channel;\n"),
               after(T_MAPPER, T_MAPPER_RISK, T_MAPPER_CHANNEL),
               Edit(T_MAPPER, '                List.of("VELOCITY_OK"));\n',
                    '                List.of("VELOCITY_OK"),\n                Channel.CARD_PRESENT);\n'),
               before(T_MAPPER, "    @Test\n    void eventValidatesAgainstTheSchema() {\n",
                      _test_method(T_MAPPER, "channelDefaultsToEcom")),
           )),
    Commit("2023-11-07 16:20", "ravi.iyer",
           "feat(api): Idempotency-Key for safe retries\n\n"
           "Acquirers retry on timeouts and we were publishing some authorisations\n"
           "twice. A retry with the same key and the same body now returns the\n"
           "original auth_id without publishing; the same key with a different body\n"
           "is a 409. Keys are kept for 24h in memory: merchants are pinned to pods by\n"
           "the load balancer, so a per-pod store is enough.\n\n"
           "Refs: PAY-366",
           (
               head(IDEM),
               head(T_IDEM),
               head(REJ),
               after(CTRL, "import java.time.Clock;\n", "import java.util.Optional;\n"),
               after(CTRL, "import org.springframework.web.bind.annotation.RequestBody;\n",
                     "import org.springframework.web.bind.annotation.RequestHeader;\n"),
               after(CTRL, "import com.dss26.payments.gateway.events.CardAuthEventMapper;\n",
                     "import com.dss26.payments.gateway.idempotency.IdempotencyStore;\n"),
               after(CTRL, "    private final Clock clock;\n", "    private final IdempotencyStore idempotency;\n"),
               Edit(CTRL, "            Clock clock) {\n", "            Clock clock,\n            IdempotencyStore idempotency) {\n"),
               after(CTRL, "        this.clock = clock;\n", "        this.idempotency = idempotency;\n"),
               Edit(CTRL,
                    "    public ResponseEntity<AuthorisationAccepted> authorise(@Valid @RequestBody AuthorisationRequest request) {\n",
                    "    public ResponseEntity<AuthorisationAccepted> authorise(\n"
                    "            @Valid @RequestBody AuthorisationRequest request,\n"
                    "            @RequestHeader(name = \"Idempotency-Key\", required = false) String idempotencyKey) {\n"),
               after(CTRL, "        String authId = UUID.randomUUID().toString();\n", CTRL_IDEMPOTENCY),
               before(HANDLER, "    @ExceptionHandler(PublishFailedException.class)\n",
                      "    @ExceptionHandler(AuthorisationRejectedException.class)\n"
                      "    ResponseEntity<ProblemDetail> rejected(AuthorisationRejectedException e) {\n"
                      "        return ResponseEntity.status(e.status()).body(problem(e.status(), e.code(), e.getMessage()));\n"
                      "    }\n\n"),
               Edit(PROPS, "        Duration sendTimeout) {\n", "        Duration sendTimeout,\n        Duration idempotencyTtl) {\n"),
               after(YML, "  send-timeout: 2s\n", "  idempotency-ttl: 24h\n"),
               Edit(T_CTRL, "import static org.mockito.ArgumentMatchers.any;\n",
                    "import static org.assertj.core.api.Assertions.assertThat;\n"
                    "import static org.mockito.ArgumentMatchers.any;\n"
                    "import static org.mockito.ArgumentMatchers.anyString;\n"),
               after(T_CTRL, "import static org.mockito.Mockito.mock;\n", "import static org.mockito.Mockito.times;\n"),
               after(T_CTRL, "import java.time.Clock;\n", "import java.time.Duration;\n"),
               after(T_CTRL, "import org.springframework.test.web.servlet.MockMvc;\n",
                     "import org.springframework.test.web.servlet.ResultActions;\n"),
               after(T_CTRL, "import com.dss26.payments.gateway.events.CardAuthSchema;\n",
                     "import com.dss26.payments.gateway.idempotency.IdempotencyStore;\n"),
               Edit(T_CTRL, "                publisher,\n                clock);\n",
                    "                publisher,\n                clock,\n"
                    "                new IdempotencyStore(Duration.ofHours(24), clock));\n"),
               after(T_CTRL, T_CTRL_CARD_TOKEN_END, T_CTRL_IDEMPOTENCY_TESTS),
           )),
    Commit("2023-11-30 09:35", "ravi.iyer",
           "feat(events): stamp the environment tier on every event\n\n"
           "cards-dev-euw1 now receives replayed production-shaped traffic for load\n"
           "tests, and those records were being mistaken for production ones. The\n"
           "producer writes its tier (GATEWAY_TIER) on every event; the field defaults\n"
           "to \"prod\" for readers that do not know it.\n\n"
           "Refs: PAY-371",
           (
               Write(AVSC, AVSC_V1),
               after(MAPPER, MAPPER_CHANNEL, '                .set("tier", tier)\n'),
               after(MAPPER, "    private final Schema schema;\n", "    private final String tier;\n"),
               Edit(MAPPER,
                    "    public CardAuthEventMapper(CardAuthSchema schema) {\n"
                    "        this(schema.schema());\n    }\n\n"
                    "    public CardAuthEventMapper(Schema schema) {\n"
                    "        this.schema = schema;\n    }\n",
                    "    public CardAuthEventMapper(CardAuthSchema schema, GatewayProperties properties) {\n"
                    "        this(schema.schema(), properties.tier());\n    }\n\n"
                    "    public CardAuthEventMapper(Schema schema, String tier) {\n"
                    "        this.schema = schema;\n        this.tier = tier;\n    }\n"),
               before(MAPPER, "import com.dss26.payments.gateway.api.AuthorisationRequest;\n",
                      "import com.dss26.payments.gateway.GatewayProperties;\n"),
               Edit(PROPS, "        Duration idempotencyTtl) {\n", "        Duration idempotencyTtl,\n        String tier) {\n"),
               after(YML, "  idempotency-ttl: 24h\n", "  tier: ${GATEWAY_TIER:prod}\n"),
               after(T_MAPPER, T_MAPPER_CHANNEL, '        assertThat(event.get("tier")).isEqualTo("prod");\n'),
               Edit(T_MAPPER, "new CardAuthEventMapper(schema);\n", 'new CardAuthEventMapper(schema, "prod");\n'),
               Edit(T_CTRL, "                new CardAuthEventMapper(CardAuthSchema.load()),\n",
                    '                new CardAuthEventMapper(CardAuthSchema.load(), "prod"),\n'),
           )),
    Commit("2024-01-17 10:00", "marta.silva",
           "build: Java 21 and Spring Boot 3.2\n\n"
           "Java 21 is the bank's LTS baseline for 2024. Spring Boot 3.2 brings\n"
           "virtual-thread support, which we are not switching on yet.\n\n"
           "Refs: PAY-388",
           (
               *java("17", "21"),
               boot("3.1.2", "3.2.1"),
               Edit(DOCKER, "FROM eclipse-temurin:17-jre\n", "FROM eclipse-temurin:21-jre\n"),
           )),
    Commit("2024-02-12 08:06", "platform-bot",
           "chore(deps): bump the github-actions group with 2 updates\n\n"
           "Bumps actions/checkout from 3 to 4 and actions/setup-java from 3 to 4\n"
           "(Node 20 runtime).",
           action("checkout", "3", "4") + action("setup-java", "3", "4")),
    Commit("2024-03-14 13:50", "noah.becker",
           "feat(api): per-merchant rate limit\n\n"
           "One merchant's retry storm on 2024-02-29 pushed every pod to 100% CPU and\n"
           "slowed authorisations for everybody else. Token bucket per merchant_id,\n"
           "200/s with a burst of 400 by default; over the limit is a 429 with\n"
           "Retry-After.\n\n"
           "Refs: PAY-402",
           (
               head(LIMITER),
               head(T_LIMITER),
               after(CTRL, "import com.dss26.payments.gateway.idempotency.IdempotencyStore;\n",
                     "import com.dss26.payments.gateway.policy.MerchantRateLimiter;\n"),
               after(CTRL, "    private final IdempotencyStore idempotency;\n",
                     "    private final MerchantRateLimiter rateLimiter;\n"),
               Edit(CTRL, "            IdempotencyStore idempotency) {\n",
                    "            IdempotencyStore idempotency,\n            MerchantRateLimiter rateLimiter) {\n"),
               after(CTRL, "        this.idempotency = idempotency;\n", "        this.rateLimiter = rateLimiter;\n"),
               before(CTRL, "        String authId = UUID.randomUUID().toString();\n", CTRL_RATE_LIMIT),
               after(REJ, '" was already used for a different request");\n    }\n',
                     "\n"
                     "    public static AuthorisationRejectedException rateLimited(String merchantId) {\n"
                     "        return new AuthorisationRejectedException(HttpStatus.TOO_MANY_REQUESTS, \"rate_limited\",\n"
                     "                \"Merchant \" + merchantId + \" is over its authorisation rate limit\");\n"
                     "    }\n"),
               before(HANDLER, "import org.springframework.http.HttpStatus;\n", "import org.springframework.http.HttpHeaders;\n"),
               Edit(HANDLER,
                    "        return ResponseEntity.status(e.status()).body(problem(e.status(), e.code(), e.getMessage()));\n",
                    "        ResponseEntity.BodyBuilder response = ResponseEntity.status(e.status());\n"
                    "        if (e.status() == HttpStatus.TOO_MANY_REQUESTS) {\n"
                    "            response.header(HttpHeaders.RETRY_AFTER, \"1\");\n"
                    "        }\n"
                    "        return response.body(problem(e.status(), e.code(), e.getMessage()));\n"),
               Edit(PROPS, "        String tier) {\n}\n",
                    "        String tier,\n        RateLimit rateLimit) {\n\n"
                    "    public record RateLimit(int perSecond, int burst) {\n    }\n}\n"),
               after(YML, "  tier: ${GATEWAY_TIER:prod}\n",
                     "  rate-limit:\n"
                     "    per-second: ${GATEWAY_RATE_LIMIT_PER_SECOND:200}\n"
                     "    burst: ${GATEWAY_RATE_LIMIT_BURST:400}\n"),
               after(T_CTRL, "import static org.mockito.Mockito.verifyNoInteractions;\n",
                     "import static org.mockito.Mockito.when;\n"),
               after(T_CTRL, "import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;\n",
                     "import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;\n"),
               after(T_CTRL, "import com.dss26.payments.gateway.idempotency.IdempotencyStore;\n",
                     "import com.dss26.payments.gateway.policy.MerchantRateLimiter;\n"),
               after(T_CTRL, "    private final AuthorisationEventPublisher publisher = mock(AuthorisationEventPublisher.class);\n",
                     "    private final MerchantRateLimiter rateLimiter = mock(MerchantRateLimiter.class);\n"),
               Edit(T_CTRL, "    void setUp() {\n        AuthorisationController controller",
                    "    void setUp() {\n        when(rateLimiter.tryAcquire(anyString())).thenReturn(true);\n"
                    "        AuthorisationController controller"),
               Edit(T_CTRL, "                new IdempotencyStore(Duration.ofHours(24), clock));\n",
                    "                new IdempotencyStore(Duration.ofHours(24), clock),\n                rateLimiter);\n"),
               before(T_CTRL, T_CTRL_HELPER, _test_method(T_CTRL, "merchantOverItsRateLimitGets429")),
           )),
    Commit("2024-04-12 11:25", "noah.becker",
           "docs: merchant-gateway runbook\n\n"
           "What on-call needs for the alerts we actually get: publish failures,\n"
           "schema lookup errors, 429s and rollbacks.\n\n"
           "Refs: PAY-415",
           (
               head(RUNBOOK),
               Edit(README, "## Build\n\n```\nmvn verify\n```\n",
                    "## Build\n\n```\nmvn verify\n```\n\n## On-call\n\n"
                    "Runbook: [docs/runbook.md](docs/runbook.md). Paging: Opsgenie, team `payments-edge`.\n"),
           )),
    Commit("2024-06-18 15:05", "marta.silva",
           "docs: fraud-scoring is now fraud-decisioning-svc (ADR-0011)",
           (
               Edit(README, "| fraud-scoring |\n", "| fraud-decisioning-svc (`fraud-decisioning-engine`) |\n"),
               Edit(RUNBOOK, "   (fraud-scoring and the other readers): Cards Platform on-call,\n",
                    "   (fraud-decisioning-svc and the other readers): Cards Platform on-call,\n"),
           )),
    Commit("2024-06-24 08:03", "platform-bot",
           "chore(deps): bump spring-boot-starter-parent from 3.2.1 to 3.3.1\n\n"
           "Bumps org.springframework.boot:spring-boot-starter-parent from 3.2.1 to 3.3.1.",
           (boot("3.2.1", "3.3.1"),)),
    Commit("2024-08-05 08:09", "platform-bot",
           "chore(deps): bump confluent.version from 7.3.1 to 7.7.0\n\n"
           "Bumps io.confluent:kafka-avro-serializer and\n"
           "io.confluent:kafka-schema-registry-maven-plugin from 7.3.1 to 7.7.0.",
           (confluent("7.3.1", "7.7.0"),)),
    Commit("2024-10-08 10:30", "marta.silva",
           "ci: run the shared schema-compat check on every pull request\n\n"
           "Action item from INC-2024-09-12-003 for every cards repo: test the .avsc\n"
           "against the registry subject before merge, not only when the release\n"
           "workflow registers it. Uses the reusable workflow in cards-ci-workflows,\n"
           "so the check is the same in every repo.\n\n"
           "Refs: PAY-431",
           (
               after(CI, "        run: mvn -B verify\n",
                     "\n"
                     "  schema-compat:\n"
                     "    uses: dss26-org/cards-ci-workflows/.github/workflows/schema-compat.yml@main\n"
                     "    with:\n"
                     "      schemas: |\n"
                     "        cards.authorisation.requested.v1-value=src/main/avro/cards.authorisation.requested.v1.avsc\n"),
               Edit(README, "on every merge to `main`. New\nfields need a default.\n",
                    "on every merge to `main`. New\nfields need a default; `schema-compat` in CI checks every pull request\n"
                    "against the subject first.\n"),
           )),
    Commit("2024-10-16 09:40", "ravi.iyer",
           "fix(deps): pin org.apache.avro:avro to 1.11.4 (CVE-2024-47561)\n\n"
           "kafka-avro-serializer 7.7.0 still brings in Avro 1.11.3, which is\n"
           "affected by CVE-2024-47561. We only parse our own .avsc, but the image\n"
           "scan blocks the release. Pin Avro explicitly until Confluent catches up.\n\n"
           "Refs: PAY-438",
           (
               before(POM, "        <schema.registry.url>",
                      "        <!-- Above the version kafka-avro-serializer brings in: CVE-2024-47561. -->\n"
                      "        <avro.version>1.11.4</avro.version>\n"),
               after(POM, POM_SERIALIZER, POM_AVRO),
           )),
    Commit("2024-12-11 14:15", "noah.becker",
           "feat(api): reject amounts with more decimals than the currency allows\n\n"
           "JPY amounts with cents and EUR amounts with a third decimal were reaching\n"
           "fraud decisioning and the ledger, which round them differently. Refuse\n"
           "them at the edge with 422 invalid_amount_scale, using the ISO 4217 minor\n"
           "unit from java.util.Currency.\n\n"
           "Refs: PAY-447",
           (
               head(POLICY),
               head(T_POLICY),
               after(CTRL, "import com.dss26.payments.gateway.idempotency.IdempotencyStore;\n",
                     "import com.dss26.payments.gateway.policy.AuthorisationPolicy;\n"),
               after(CTRL, "    private final MerchantRateLimiter rateLimiter;\n", "    private final AuthorisationPolicy policy;\n"),
               Edit(CTRL, "            MerchantRateLimiter rateLimiter) {\n",
                    "            MerchantRateLimiter rateLimiter,\n            AuthorisationPolicy policy) {\n"),
               after(CTRL, "        this.rateLimiter = rateLimiter;\n", "        this.policy = policy;\n"),
               Edit(CTRL,
                    "            throw AuthorisationRejectedException.rateLimited(request.merchantId());\n        }\n\n",
                    "            throw AuthorisationRejectedException.rateLimited(request.merchantId());\n        }\n"
                    "        policy.check(request);\n\n"),
               after(T_CTRL, "import com.dss26.payments.gateway.idempotency.IdempotencyStore;\n",
                     "import com.dss26.payments.gateway.policy.AuthorisationPolicy;\n"),
               Edit(T_CTRL, "                rateLimiter);\n", "                rateLimiter,\n                new AuthorisationPolicy());\n"),
               before(T_CTRL, T_CTRL_HELPER, _test_method(T_CTRL, "yenWithMinorUnitsIs422")),
           )),
    Commit("2025-03-13 10:20", "ravi.iyer",
           "chore(ops): page through PagerDuty (PSVC17D)\n\n"
           "Paging moved off Opsgenie. Backstage now points at the PagerDuty service\n"
           "and the runbook has the new escalation path and the Datadog monitors.\n\n"
           "Refs: PAY-470",
           (
               Edit(CATALOG, "    opsgenie.com/team: payments-edge\n", "    pagerduty.com/service-id: PSVC17D\n"),
               after(CATALOG, "      title: ADR-0007 - Avro and Schema Registry for card events\n",
                     "    - url: https://dss26.pagerduty.com/service-directory/PSVC17D\n"
                     "      title: PagerDuty - merchant-gateway\n"),
               Edit(RUNBOOK,
                    "Paging: Opsgenie, team `payments-edge`.\n"
                    "Dashboards and logs: Grafana (`Merchant gateway`) and Kibana (`app:merchant-gateway`).\n",
                    "Paging: PagerDuty service `merchant-gateway` (PSVC17D), Payments Edge on-call.\n"
                    "Dashboards, logs and monitors: Datadog EU, `service:merchant-gateway`.\n"),
               Edit(RUNBOOK, "1. Payments Edge on-call (Opsgenie).\n", "1. Payments Edge on-call (PagerDuty).\n"),
               Edit(RUNBOOK, "   escalation in Opsgenie, `#cards-platform`.\n",
                    "   escalation policy \"Cards Platform - Primary\", `#cards-platform`.\n"),
               Edit(README, "Paging: Opsgenie, team `payments-edge`.\n",
                    "Paging: PagerDuty, service `merchant-gateway` (PSVC17D).\n"),
           )),
    Commit("2025-05-22 15:45", "noah.becker",
           "perf(producer): lz4 and linger.ms=5\n\n"
           "At peak most produce requests carried a single record. A 5ms linger with\n"
           "lz4 halves the request rate to the brokers; p99 end-to-end latency in the\n"
           "cards-dev-euw1 load test did not move.\n\n"
           "Refs: PAY-489",
           (Edit(YML,
                 "      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer\n"
                 "      properties:\n        enable.idempotence: true\n        delivery.timeout.ms: 30000\n",
                 "      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer\n"
                 "      compression-type: lz4\n"
                 "      properties:\n        enable.idempotence: true\n        linger.ms: 5\n"
                 "        delivery.timeout.ms: 30000\n"),)),
    Commit("2025-07-07 08:02", "platform-bot",
           "chore(deps): bump spring-boot-starter-parent from 3.3.1 to 3.3.13\n\n"
           "Bumps org.springframework.boot:spring-boot-starter-parent from 3.3.1 to 3.3.13.",
           (boot("3.3.1", "3.3.13"),)),
    Commit("2025-10-13 08:07", "platform-bot",
           "chore(deps): bump confluent.version from 7.7.0 to 7.7.5\n\n"
           "Bumps io.confluent:kafka-avro-serializer and\n"
           "io.confluent:kafka-schema-registry-maven-plugin from 7.7.0 to 7.7.5.",
           (confluent("7.7.0", "7.7.5"),)),
    Commit("2025-11-19 11:10", "marta.silva",
           "docs(readme): rewrite for on-call and consumers\n\n"
           "The README still read like the kafka-dc1 days. Rewritten around what\n"
           "people ask us: the API and its error codes, the event we produce and who\n"
           "reads it, how a schema change ships, and where the runbook is. Matches\n"
           "the service page in the DSS26 space.\n\n"
           "Refs: PAY-503",
           (head(README),)),
    Commit("2026-01-21 10:35", "ravi.iyer",
           "feat(events): pass X-Request-Id through as a Kafka header\n\n"
           "Merchants quote their request id when they call support. Copying it onto\n"
           "the event as x-request-id lets fraud decisioning and txn-history log it\n"
           "next to auth_id.\n\n"
           "Refs: PAY-521",
           (
               Edit(PUB, "import java.time.Duration;\n", "import java.nio.charset.StandardCharsets;\nimport java.time.Duration;\n"),
               after(PUB, "import org.apache.avro.generic.GenericRecord;\n",
                     "import org.apache.kafka.clients.producer.ProducerRecord;\n"),
               Edit(PUB, "public class AuthorisationEventPublisher {\n\n    private static final Logger log",
                    "public class AuthorisationEventPublisher {\n\n"
                    "    static final String REQUEST_ID_HEADER = \"x-request-id\";\n\n"
                    "    private static final Logger log"),
               Edit(PUB,
                    "    public void publish(String key, GenericRecord event) {\n"
                    "        try {\n"
                    "            kafka.send(topic, key, event).get(sendTimeout.toMillis(), TimeUnit.MILLISECONDS);\n",
                    "    public void publish(String key, GenericRecord event, String requestId) {\n"
                    "        ProducerRecord<String, GenericRecord> record = new ProducerRecord<>(topic, key, event);\n"
                    "        if (requestId != null && !requestId.isBlank()) {\n"
                    "            record.headers().add(REQUEST_ID_HEADER, requestId.getBytes(StandardCharsets.UTF_8));\n"
                    "        }\n"
                    "        try {\n"
                    "            kafka.send(record).get(sendTimeout.toMillis(), TimeUnit.MILLISECONDS);\n"),
               Edit(CTRL,
                    "            @RequestHeader(name = \"Idempotency-Key\", required = false) String idempotencyKey) {\n",
                    "            @RequestHeader(name = \"Idempotency-Key\", required = false) String idempotencyKey,\n"
                    "            @RequestHeader(name = \"X-Request-Id\", required = false) String requestId) {\n"),
               Edit(CTRL, "        publisher.publish(request.cardToken(), event);\n",
                    "        publisher.publish(request.cardToken(), event, requestId);\n"),
               head(T_PUB),
               after(T_CTRL, "import static org.mockito.ArgumentMatchers.eq;\n",
                     "import static org.mockito.ArgumentMatchers.isNull;\n"),
               Edit(T_CTRL,
                    "        verify(publisher).publish(eq(\"tok_4410982\"), any(GenericRecord.class));\n",
                    "        verify(publisher).publish(eq(\"tok_4410982\"), any(GenericRecord.class), isNull());\n"),
               Edit(T_CTRL, "        verify(publisher, times(1)).publish(anyString(), any());\n",
                    "        verify(publisher, times(1)).publish(anyString(), any(), any());\n"),
               before(T_CTRL, T_CTRL_HELPER, _test_method(T_CTRL, "passesTheRequestIdToThePublisher")),
               after(README, "and publishes nothing; keys are kept for 24h. |\n",
                     "| `X-Request-Id` | Optional. Copied onto the event as the `x-request-id` Kafka header. |\n"),
           )),
    Commit("2026-03-05 09:50", "noah.becker",
           "fix(idempotency): scope Idempotency-Key per merchant\n\n"
           "Two merchants on the same acquirer SDK generated colliding keys on\n"
           "2026-02-24, and the second one got a 409 for a request it had never\n"
           "sent. Keys are now namespaced by merchant_id.\n\n"
           "Refs: PAY-536",
           (
               Edit(CTRL, "idempotency.reserve(idempotencyKey, request, authId);",
                    "idempotency.reserve(request.merchantId() + \":\" + idempotencyKey, request, authId);"),
               before(T_CTRL, T_CTRL_HELPER, _test_method(T_CTRL, "sameKeyFromTwoMerchantsIsTwoAuthorisations")),
               Edit(README, "and publishes nothing; keys are kept for 24h. |\n",
                    "and publishes nothing; keys are scoped per merchant and kept for 24h. |\n"),
           )),
    Commit("2026-08-28 14:30", "noah.becker",
           "test(api): cover malformed JSON and unknown channels\n\n"
           "Both already come back as 400 from message conversion; these tests keep\n"
           "it that way.\n\n"
           "Refs: PAY-548",
           (before(T_CTRL, T_CTRL_HELPER,
                   _test_method(T_CTRL, "malformedJsonIs400") + _test_method(T_CTRL, "unknownChannelIs400")),)),
    Commit("2026-09-14 08:04", "platform-bot",
           "chore(deps): bump org.apache.avro:avro from 1.11.4 to 1.11.5\n\n"
           "Bumps org.apache.avro:avro from 1.11.4 to 1.11.5.",
           (Edit(POM, "<avro.version>1.11.4</avro.version>", "<avro.version>1.11.5</avro.version>"),)),
)

HISTORY = _rewind(_HISTORY)


# ---------------------------------------------------------------------------
# Pull requests opened live by the scenario engine
# ---------------------------------------------------------------------------

DECOY_CURRENCY = ScenarioPR(
    key="gateway-unknown-currency-422",
    kind="decoy",
    scenario="consumer-lag",
    branch="noah/unknown-currency-422",
    title="fix(api): reject unknown currency codes with 422 instead of 500 (PAY-561)",
    body=(
        "## What\n"
        "A three-letter code that is not an ISO 4217 currency (`ZZZ`, `EUD`) passes bean "
        "validation and then throws `IllegalArgumentException` from `Currency.getInstance` in "
        "`AuthorisationPolicy`, which the merchant sees as a 500. Return "
        "422 `unsupported_currency` instead.\n\n"
        "## Why\n"
        "Two acquirer test integrations hit this last week. Acquirers retry 5xx, so a typo in "
        "a currency code turns into a retry loop instead of a fixed request, and it shows up "
        "in our 5xx monitor.\n\n"
        "## Schema impact\n"
        "None. No change to the event or to `src/main/avro`.\n\n"
        "## Testing\n"
        "New `AuthorisationPolicyTest` case. CI green.\n\n"
        "## Rollout and rollback\n"
        "Standard release on merge. Rollback = revert this PR."
    ),
    author="noah.becker",
    commit_message="fix(api): reject unknown currency codes with 422 instead of 500 (PAY-561)",
    ops=(
        Edit(POLICY,
             "        Currency currency = Currency.getInstance(request.currency());\n",
             "        Currency currency;\n"
             "        try {\n"
             "            currency = Currency.getInstance(request.currency());\n"
             "        } catch (IllegalArgumentException e) {\n"
             "            throw new AuthorisationRejectedException(HttpStatus.UNPROCESSABLE_ENTITY, \"unsupported_currency\",\n"
             "                    request.currency() + \" is not an ISO 4217 currency code\");\n"
             "        }\n"),
        Edit(T_POLICY,
             "        assertThatThrownBy(() -> policy.check(request(\"42.505\", \"EUR\")))\n"
             "                .isInstanceOf(AuthorisationRejectedException.class);\n"
             "    }\n\n"
             "    private static",
             "        assertThatThrownBy(() -> policy.check(request(\"42.505\", \"EUR\")))\n"
             "                .isInstanceOf(AuthorisationRejectedException.class);\n"
             "    }\n\n"
             "    @Test\n"
             "    void rejectsCodesThatAreNotIso4217CurrenciesWith422() {\n"
             "        assertThatThrownBy(() -> policy.check(request(\"10.00\", \"ZZZ\")))\n"
             "                .isInstanceOfSatisfying(AuthorisationRejectedException.class, e -> {\n"
             "                    assertThat(e.status()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);\n"
             "                    assertThat(e.code()).isEqualTo(\"unsupported_currency\");\n"
             "                });\n"
             "    }\n\n"
             "    private static"),
    ),
    labels=("bug", "api"),
)

CULPRIT_DECIMAL_AMOUNT = ScenarioPR(
    key="gateway-decimal-amount",
    kind="culprit",
    scenario="consumer-lag",
    branch="ravi/decimal-amount-cards-1502",
    title="feat(auth-events): publish amount as a decimal string, drop country (CARDS-1502)",
    body=(
        "## What\n"
        "Implements the decimal-amount change for `cards.authorisation.requested.v1` planned at "
        "the 2026-04-29 ops review (CARDS-1502):\n\n"
        "- `amount` is published as a decimal string in major units "
        "(`BigDecimal.toPlainString()`, e.g. `\"1250.375\"`) instead of a `double`.\n"
        "- `country` is no longer sent.\n\n"
        "The REST API does not change: `amount` and `merchantCountry` are accepted and "
        "validated exactly as before.\n\n"
        "## Why\n"
        "- A `double` cannot hold most decimal amounts exactly. We receive exact decimals from "
        "acquirers and then publish a binary approximation; for three-decimal currencies (KWD, "
        "BHD) and large JPY amounts the difference shows up in reconciliation. A decimal string "
        "carries the acquirer's amount as sent.\n"
        "- `country` duplicates what the merchant registry holds for every `merchant_id`, so "
        "consumers can derive it from there. It is also the field acquirers most often get "
        "wrong.\n\n"
        "## Schema impact\n"
        "- `src/main/avro/cards.authorisation.requested.v1.avsc`: `amount` double -> string, "
        "`country` removed.\n"
        "- The registry rejected the new version as BACKWARD-incompatible (409 against the "
        "latest version), so `pom.xml` sets the subject's compatibility to `NONE` for the "
        "rollout. The release workflow applies it before registering. We restore `BACKWARD` "
        "once consumers have migrated to the new version.\n"
        "- Fraud decisioning were informed at the ops review.\n\n"
        "## Testing\n"
        "- `CardAuthEventMapperTest` updated for the string amount, plus a three-decimal "
        "(KWD) case.\n"
        "- CI green.\n\n"
        "## Rollout and rollback\n"
        "Normal change CHG-4471. Merge releases it: compatibility, register, deploy. "
        "Rollback = revert this PR."
    ),
    author="ravi.iyer",
    commit_message=(
        "feat(auth-events): publish amount as a decimal string, drop country (CARDS-1502)\n\n"
        "amount is now BigDecimal.toPlainString() in major units and country is no\n"
        "longer sent; the subject goes to NONE for the rollout."
    ),
    ops=(
        Edit(AVSC, AVSC_V1, AVSC_V2),
        Edit(POM, COMPAT_BACKWARD, COMPAT_NONE),
        Edit(MAPPER,
             '                .set("amount", request.amount().doubleValue())\n'
             '                .set("currency", request.currency())\n'
             '                .set("country", request.merchantCountry())\n',
             '                .set("amount", request.amount().toPlainString())\n'
             '                .set("currency", request.currency())\n'),
        Edit(T_MAPPER,
             '        assertThat(event.get("amount")).isEqualTo(42.5);\n'
             '        assertThat(event.get("currency")).isEqualTo("EUR");\n'
             '        assertThat(event.get("country")).isEqualTo("FR");\n'
             '        assertThat(event.get("ts")).isEqualTo(RECEIVED_AT.toEpochMilli());\n'
             '        assertThat(event.get("risk_signals")).isEqualTo(List.of("VELOCITY_OK"));\n'
             '        assertThat(event.get("channel")).isEqualTo("CARD_PRESENT");\n'
             '        assertThat(event.get("tier")).isEqualTo("prod");\n'
             '    }\n',
             '        assertThat(event.get("amount")).isEqualTo("42.50");\n'
             '        assertThat(event.get("currency")).isEqualTo("EUR");\n'
             '        assertThat(event.get("ts")).isEqualTo(RECEIVED_AT.toEpochMilli());\n'
             '        assertThat(event.get("risk_signals")).isEqualTo(List.of("VELOCITY_OK"));\n'
             '        assertThat(event.get("channel")).isEqualTo("CARD_PRESENT");\n'
             '        assertThat(event.get("tier")).isEqualTo("prod");\n'
             '    }\n\n'
             '    @Test\n'
             '    void keepsEveryDecimalPlaceOfTheAmount() {\n'
             '        AuthorisationRequest dinar = new AuthorisationRequest("mch_halcyon_retail", "tok_7730215",\n'
             '                new BigDecimal("1250.375"), "KWD", "KW", List.of(), Channel.ECOM);\n\n'
             '        assertThat(mapper.toEvent(AUTH_ID, dinar, RECEIVED_AT).get("amount")).isEqualTo("1250.375");\n'
             '    }\n'),
    ),
    labels=("schema", "kafka", "tier-1"),
    revert_author="marta.silva",
    revert_body=(
        "Reverts the CARDS-1502 decimal-amount change. fraud-decisioning-engine reads "
        "cards.authorisation.requested.v1 with the v1 schema and cannot read records written "
        "with the new version, so it stopped at the first one and ledger postings stopped "
        "behind it. Merging this restores BACKWARD on the subject; the version registered by "
        "the release still has to be removed from the registry. CARDS-1502 goes back to the "
        "agreed order: fraud-decisioning upgrades first, then the producer."
    ),
)

PRS: tuple[ScenarioPR, ...] = (DECOY_CURRENCY, CULPRIT_DECIMAL_AMOUNT)


REPO_SPEC = RepoSpec(
    name=REPO,
    description=(
        "Merchant and acquirer edge: card authorisation requests over REST, published as "
        "cards.authorisation.requested.v1 (Avro)."
    ),
    team="payments-edge",
    domain="cards",
    tier="A",
    topics=("java", "spring-boot", "kafka", "avro", "team-payments-edge", "domain-cards", "tier-1"),
    history=HISTORY,
    prs=PRS,
    labels=DEFAULT_LABELS + (
        Label("schema", "5319e7", "Changes an Avro schema or its subject settings"),
        Label("kafka", "1d76db", "Kafka producer or topic configuration"),
        Label("api", "c5def5", "Merchant-facing REST API"),
    ),
    team_access=(("platform-engineering", "push"), ("cards-platform", "triage")),
)
