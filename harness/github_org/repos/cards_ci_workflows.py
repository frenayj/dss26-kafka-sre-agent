"""dss26-org/cards-ci-workflows - reusable GitHub Actions workflows for the cards repos.

Story role (schema break): the guardrail that was switched off.

* ``schema-compat.yml`` is a real reusable workflow (``on: workflow_call``,
  one required ``schemas`` input, a single ``compat`` job): throwaway Kafka +
  Schema Registry service containers, base versions registered, the pull
  request's versions checked with ``/compatibility/subjects/<subject>/versions/latest``.
  merchant-gateway and fraud-decisioning-svc call it.
* Created by priya.r in October 2024 as the INC-2024-09-12-003 action item.
  jordan.k tries to fix the flaky registry container in January and February
  2026, then on 2026-04-15 disables the job with ``if: ${{ false }}``
  (CARDS-1423, agreed at that day's ops review). Nothing re-enables it, so
  callers show the check as skipped - which is how the culprit schema merges.

No scenario PRs live here; the evidence is the history itself.
"""

from __future__ import annotations

from model import DEFAULT_LABELS, FILES_ROOT, Commit, RepoSpec, Write

from repos.kafka_platform import Versions, between_pair, def_pair, line_pair

REPO = "cards-ci-workflows"
F = "cards-ci-workflows"

WF = ".github/workflows"
ACTION = ".github/actions/schema-compat"


def _src(path: str) -> str:
    return (FILES_ROOT / F / path).read_text()


def _d(name: str):
    return lambda text: def_pair(text, name)


def _l(line: str):
    return lambda text: line_pair(text, line)


# ---------------------------------------------------------------------------
# File versions, rewound from the final files under files/cards-ci-workflows/
# ---------------------------------------------------------------------------

SCRIPT = Versions(_src(f"{ACTION}/schema_compat.py"), [
    ("zero-sha", [
        ("    if not args.base_ref:\n",
         "    # Pushes that create a branch carry an all-zero \"before\" SHA.\n"
         "    if not args.base_ref.strip(\"0\"):\n"),
    ]),
    ("registry-wait", [
        _l("import time\n"),
        _d("wait_until_ready"),
        _l("    registry.wait_until_ready()\n"),
    ]),
])

TESTS = Versions(_src("tests/test_schema_compat.py"), [
    ("zero-sha", [_d("test_branch_creation_push_is_skipped")]),
    ("registry-wait", [_l("        self.registry.wait_until_ready()\n")]),
])

COMPAT = Versions(_src(f"{WF}/schema-compat.yml"), [
    ("registry-wait", [
        _l('          SCHEMA_REGISTRY_KAFKASTORE_INIT_TIMEOUT_MS: "120000"\n'),
        ("          --health-timeout 5s\n          --health-retries 12\n",
         "          --health-timeout 5s\n          --health-retries 18\n"),
    ]),
    ("broker-health", [
        lambda t: between_pair(t, "          KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1\n",
                               "      schema-registry:\n"),
    ]),
    ("disable", [
        lambda t: between_pair(t, "    name: Avro schema compatibility\n",
                               "    runs-on: ubuntu-latest\n"),
    ]),
])

JAVA = Versions(_src(f"{WF}/java-build.yml"), [
    ("working-directory", [
        lambda t: between_pair(t, "        default: -B -ntp verify\n", "\npermissions:"),
        lambda t: between_pair(t, "    timeout-minutes: 30\n", "    steps:\n"),
        ("          path: \"**/target/surefire-reports/\"\n",
         "          path: ${{ inputs.working-directory }}/**/target/surefire-reports/\n"),
    ]),
])

README = Versions(_src("README.md"), [
    ("first-callers", [(
        "| None yet | | |\n",
        "| `merchant-gateway` | payments-edge | 2024-10 |\n"
        "| `fraud-decisioning-svc` | cards-platform | 2024-10 |\n",
    )]),
    ("clearing", [_l("| `clearing-settlement-svc` | clearing-settlement | 2024-11 |\n")]),
    ("disputes", [_l("| `disputes-svc` | cards-servicing | 2024-11 |\n")]),
    ("java-build", [
        _l("| [`java-build.yml`](.github/workflows/java-build.yml) | Maven build and unit tests "
           "on Temurin, with the Maven cache |\n"),
    ]),
])

# Pinned versions, as they change over time. The final files carry the last
# value of each; earlier commits substitute their own.
FINAL_PINS = {
    "confluentinc/cp-kafka:": "7.9.1", "confluentinc/cp-schema-registry:": "7.9.1",
    "actions/checkout@": "v5", "rhysd/actionlint:": "1.7.7",
    "actions/setup-java@": "v5", "actions/upload-artifact@": "v5",
}


def _pin(text: str, pins: dict[str, str]) -> str:
    for prefix, version in pins.items():
        text = text.replace(prefix + FINAL_PINS[prefix], prefix + version)
    return text


CATALOG_INFO = """\
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: cards-ci-workflows
  title: Cards CI workflows
  description: Reusable GitHub Actions workflows for the cards repositories, including schema-compat.
  annotations:
    github.com/project-slug: dss26-org/cards-ci-workflows
  tags: [ci, github-actions, schema-registry, avro]
  links:
    - url: https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980001323/INC-2024-09-12-003+Incompatible+schema+on+cards.clearing.matched.v1
      title: INC-2024-09-12-003 - Incompatible schema on cards.clearing.matched.v1
    - url: https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980066817/Schema+evolution+policy+for+card+events
      title: Schema evolution policy for card events
spec:
  type: library
  lifecycle: production
  owner: group:cards-platform
  system: cards-kafka-platform
"""

CODEOWNERS = """\
# Callers use @main: every change here lands in every cards repo's CI.
*                 @dss26-org/cards-platform
"""

PR_TEMPLATE = """\
## What

## Why

## Tested with
<!-- Which caller ran this branch (uses: ...@<branch>), and a link to the run. -->
"""

GITIGNORE = "__pycache__/\n*.pyc\n"


class _Tree:
    """Render the repo after every change and commit only what differs."""

    def __init__(self) -> None:
        self.state = {
            "script": None, "tests": None, "compat": None, "java": None, "readme": None,
            "java_present": False,
        }
        self.pins = {
            "confluentinc/cp-kafka:": "7.7.1", "confluentinc/cp-schema-registry:": "7.7.1",
            "actions/checkout@": "v4", "rhysd/actionlint:": "1.7.3",
            "actions/setup-java@": "v4", "actions/upload-artifact@": "v4",
        }
        self.tree: dict[str, str] = {}
        self.commits: list[Commit] = []

    def render(self) -> dict[str, str]:
        s = self.state
        files = {
            "README.md": README.at(s["readme"]),
            "catalog-info.yaml": CATALOG_INFO,
            ".github/CODEOWNERS": CODEOWNERS,
            ".github/pull_request_template.md": PR_TEMPLATE,
            ".gitignore": GITIGNORE,
            f"{WF}/schema-compat.yml": _pin(COMPAT.at(s["compat"]), self.pins),
            f"{WF}/ci.yml": _pin(_src(f"{WF}/ci.yml"), self.pins),
            f"{ACTION}/action.yml": _src(f"{ACTION}/action.yml"),
            f"{ACTION}/schema_compat.py": SCRIPT.at(s["script"]),
            "tests/test_schema_compat.py": TESTS.at(s["tests"]),
        }
        for name in ("clearing_matched_v1", "clearing_matched_v1_optional_field",
                     "clearing_matched_v1_required_field"):
            files[f"tests/schemas/{name}.avsc"] = _src(f"tests/schemas/{name}.avsc")
        if s["java_present"]:
            files[f"{WF}/java-build.yml"] = _pin(JAVA.at(s["java"]), self.pins)
        return files

    def commit(self, when: str, author: str, message: str) -> None:
        files = self.render()
        ops = tuple(Write(p, files[p], executable=p.endswith("schema_compat.py"))
                    for p in sorted(files) if self.tree.get(p) != files[p])
        if not ops:
            raise ValueError(f"{REPO}: empty commit {message.splitlines()[0]!r}")
        self.commits.append(Commit(when, author, message, ops))
        self.tree = files


def _build_history() -> tuple[Commit, ...]:
    t = _Tree()
    s = t.state

    t.commit("2024-10-03 10:20", "priya.r",
             "feat: reusable schema-compat workflow for the cards repos\n\n"
             "Action item from INC-2024-09-12-003: an incompatible schema on\n"
             "cards.clearing.matched.v1 was registered without review and the clearing\n"
             "consumers stopped. Callers pass <subject>=<path> pairs; the workflow\n"
             "starts a throwaway Kafka and Schema Registry, registers the base\n"
             "branch's version of each schema and asks the registry whether the pull\n"
             "request's version is BACKWARD compatible with it.\n\n"
             "The check lives in a composite action next to the workflow, so the\n"
             "runner fetches it with the workflow and callers need no extra token.\n\n"
             "Refs: CARDS-1152")

    s["readme"] = "first-callers"
    t.commit("2024-10-08 16:45", "priya.r",
             "docs(readme): merchant-gateway and fraud-decisioning-svc call schema-compat\n\n"
             "Both producers of the Tier-1 card topics run it on every pull request,\n"
             "as a required check on main.")

    s["script"] = s["tests"] = "zero-sha"
    t.commit("2024-10-22 11:10", "priya.r",
             "fix(schema-compat): skip pushes that create a branch\n\n"
             "github.event.before is all zeros on the first push of a new branch, and\n"
             "git show 0000000:<path> failed the job instead of skipping it.")

    s["readme"] = "clearing"
    t.commit("2024-11-12 14:00", "henrik.larsen",
             "docs(readme): clearing-settlement-svc calls schema-compat")

    s["readme"] = "disputes"
    t.commit("2024-11-26 10:30", "chloe.dubois",
             "docs(readme): add disputes-svc to the schema-compat callers")

    s["java_present"] = True
    s["readme"] = "java-build"
    t.commit("2025-01-14 15:20", "alex.chen",
             "feat: reusable java-build workflow\n\n"
             "The same Maven verify job was copied into five service repos with five\n"
             "different cache setups. One version here, with the Maven cache and the\n"
             "surefire reports uploaded when the build fails.")

    t.pins["rhysd/actionlint:"] = "1.7.7"
    t.commit("2025-02-04 09:00", "platform-bot", "chore(deps): bump rhysd/actionlint from 1.7.3 to 1.7.7")

    t.pins["confluentinc/cp-kafka:"] = t.pins["confluentinc/cp-schema-registry:"] = "7.9.0"
    t.commit("2025-03-18 09:00", "platform-bot",
             "chore(deps): bump confluentinc/cp-kafka and cp-schema-registry from 7.7.1 to 7.9.0")

    t.pins["confluentinc/cp-kafka:"] = t.pins["confluentinc/cp-schema-registry:"] = "7.9.1"
    t.commit("2025-06-10 09:00", "platform-bot",
             "chore(deps): bump confluentinc/cp-kafka and cp-schema-registry from 7.9.0 to 7.9.1")

    t.pins["actions/checkout@"] = "v5"
    t.commit("2025-09-02 08:15", "platform-bot", "chore(deps): bump actions/checkout from 4 to 5")

    t.pins["actions/setup-java@"] = "v5"
    t.commit("2025-09-16 08:20", "platform-bot", "chore(deps): bump actions/setup-java from 4 to 5")

    t.pins["actions/upload-artifact@"] = "v5"
    t.commit("2025-11-04 09:00", "platform-bot", "chore(deps): bump actions/upload-artifact from 4 to 5")

    s["script"] = s["tests"] = s["compat"] = "registry-wait"
    t.commit("2026-01-20 11:05", "jordan.k",
             "fix(schema-compat): wait for Schema Registry and give it longer to reach Kafka\n\n"
             "About one run in five fails with \"Failed to initialize container\" on\n"
             "schema-registry: it gives up on the broker after the default 60s while\n"
             "Kafka is still formatting its log dir. Give the kafkastore 120s, let the\n"
             "health check retry for three minutes, and have the script poll\n"
             "/subjects before it registers anything.\n\nRefs: CARDS-1391")

    s["compat"] = "broker-health"
    t.commit("2026-02-17 14:40", "jordan.k",
             "fix(schema-compat): health-check the broker as well\n\n"
             "Still failing about one run in four. Both services start together, so\n"
             "the registry keeps racing the broker. A broker health check does not\n"
             "order them, but the job log now shows which container never came up.\n\n"
             "Refs: CARDS-1391")

    s["compat"] = "disable"
    t.commit("2026-04-15 17:20", "jordan.k",
             "ci: temporarily disable schema-compat (CARDS-1423)\n\n"
             "The schema-registry service container still fails to start on roughly\n"
             "one run in three, and because schema-compat is a required check it is\n"
             "blocking every cards PR. Skip the job until CARDS-1423 finds a reliable\n"
             "way to start the registry (agreed at today's ops review). Callers will\n"
             "show the check as skipped.\n\nRefs: CARDS-1423")

    s["java"] = "working-directory"
    t.commit("2026-05-19 10:45", "alex.chen",
             "feat(java-build): working-directory input for multi-module repos\n\n"
             "Lets a repo keep its Maven project in a subdirectory instead of the\n"
             "repository root, as the repos that also carry deployment tooling do.")

    final = t.render()
    for path in final:
        disk = FILES_ROOT / F / path
        if disk.exists():
            assert final[path] == disk.read_text(), f"{REPO}: {path} does not end as on disk"
    return tuple(t.commits)


HISTORY = _build_history()


REPO_SPEC = RepoSpec(
    name=REPO,
    description="Reusable GitHub Actions workflows for the cards repositories (schema-compat, java-build).",
    team="cards-platform",
    domain="cards",
    tier="A",
    topics=("github-actions", "ci", "schema-registry", "avro", "team-cards-platform", "domain-cards"),
    history=HISTORY,
    labels=DEFAULT_LABELS,
    team_access=(("platform-engineering", "push"),),
    actions_access_org=True,
)
