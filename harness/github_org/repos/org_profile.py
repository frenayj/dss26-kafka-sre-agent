"""dss26-org/.github-private - the member-only organisation profile.

GitHub shows ``profile/README.md`` from a private ``.github-private`` repo on
the organisation page to signed-in members. This one is the DSS26 Bank
Engineering homepage: tribes and squads (from ``people.TEAMS``) with their main
repositories, how the bank works (ADRs and runbooks in Confluence, GitOps for
Kafka, Lenses, Datadog EU, PagerDuty, CAB for Tier-1), golden paths and links.

No story role beyond backdrop. Its history tracks the same tooling changes the
Confluence space records: Control Center -> Lenses and Grafana -> Datadog in
January 2025, Opsgenie -> PagerDuty in February 2025. The golden path still
says to call schema-compat; nobody updated it when the job was disabled, the
same way the Confluence schema policy went stale.
"""

from __future__ import annotations

from model import DEFAULT_LABELS, FILES_ROOT, Commit, RepoSpec, Write
from people import TEAMS

from repos.kafka_platform import Versions, between_pair, line_pair

REPO = ".github-private"
F = ".github-private"
PROFILE = "profile/README.md"


def _src(path: str) -> str:
    return (FILES_ROOT / F / path).read_text()


def _l(line: str):
    return lambda text: line_pair(text, line)


def drop_column(section: str, index: int) -> str:
    """The same Markdown tables with column ``index`` removed."""
    out = []
    for line in section.splitlines(keepends=True):
        if not line.startswith("|"):
            out.append(line)
            continue
        cells = [c.strip() for c in line.strip()[1:-1].split("|")]
        del cells[index]
        if all(set(c) <= {"-"} for c in cells):
            out.append("|" + "|".join("---" for _ in cells) + "|\n")
        else:
            out.append("| " + " | ".join(cells) + " |\n")
    return "".join(out)


def _repos_column(text: str) -> tuple[str, str]:
    start = text.index("## Tribes and squads\n")
    end = text.index("\n## How we work")
    section = text[start:end]
    return drop_column(section, 2), section


_CI = "[cards-ci-workflows](https://github.com/dss26-org/cards-ci-workflows)"

PROFILE_VERSIONS = Versions(_src(PROFILE), [
    ("schema-compat", [
        _l(f"| Change an Avro schema on a cards topic | Call `schema-compat` from {_CI} in your "
           "CI, one subject per topic, `BACKWARD` compatible |\n"),
    ]),
    ("lenses-datadog", [
        ("- **Confluent Control Center** is the Kafka console for production: topics,\n"
         "  schemas and consumer groups. Ask Platform Engineering for access.\n",
         "- **Lenses** is the Kafka console for every environment: topics, schemas,\n"
         "  consumer groups and connectors. Access is by SSO group; write access is\n"
         "  time-boxed and approved.\n"),
        ("- **Observability**: metrics in Grafana, logs in Kibana. Dashboards are named\n"
         "  after the service.\n",
         "- **Observability** is Datadog, EU site: metrics, logs, APM and monitors.\n"
         "  Dashboards and monitors are named after the service.\n"),
        ("- Grafana: <https://grafana.dss26.internal>\n",
         "- Datadog (EU): <https://app.datadoghq.eu>\n"),
        _l("- Lenses: <https://lenses.dss26.internal>\n"),
    ]),
    ("pagerduty", [
        ("- **On-call** is Opsgenie. Every Tier-1 service has an Opsgenie team with a\n"
         "  primary and a secondary rotation. During an\n",
         "- **On-call** is PagerDuty. Every Tier-1 service has a PagerDuty service and\n"
         "  an escalation policy (for example *Cards Platform - Primary*). During an\n"),
        ("- Opsgenie: <https://dss26.app.opsgenie.com>\n",
         "- PagerDuty: <https://dss26.pagerduty.com>\n"),
    ]),
    ("repos", [
        _repos_column,
        _l(f"| Build a Java service | The `java-build` reusable workflow in {_CI} |\n"),
    ]),
    ("new-joiners", [
        lambda t: between_pair(
            t, "| Make sure the right people review | `.github/CODEOWNERS` with team handles "
               "(`@dss26-org/<squad>`), never individuals |\n",
            "\n## Useful links"),
    ]),
])

README = """\
# .github-private

The member-only profile of the dss26-org organisation. GitHub shows
[`profile/README.md`](profile/README.md) on the organisation page to
signed-in members; outside collaborators and the public never see it.

Change it with a pull request - Platform Engineering reviews. Keep it short
and stable: anything that changes every month belongs in Confluence, linked
from here.
"""

CATALOG_INFO = """\
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: github-org-profile
  title: dss26-org member profile
  description: The engineering homepage members see on the dss26-org organisation page.
  annotations:
    github.com/project-slug: dss26-org/.github-private
  tags: [documentation, onboarding]
spec:
  type: documentation
  lifecycle: production
  owner: group:platform-engineering
  system: engineering-portal
"""

CODEOWNERS = """\
*                 @dss26-org/platform-engineering
"""

MARKDOWNLINT = """\
# Tables with links make long lines unavoidable.
MD013: false
"""

LINT_WORKFLOW = """\
name: lint

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  markdown:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: DavidAnson/markdownlint-cli2-action@{version}
        with:
          globs: "**/*.md"
"""

# The squads in the profile are the squads in people.py, in the same order.
_SQUADS = [t.name for t in TEAMS if t.parent]
_TRIBES = [t.name for t in TEAMS if t.parent is None]
_text = PROFILE_VERSIONS.final
assert all(f"| {name} |" in _text for name in _SQUADS), "profile is missing a squad"
assert all(f"### {name}\n" in _text for name in _TRIBES), "profile is missing a tribe"


def _build_history() -> tuple[Commit, ...]:
    files: dict[str, str] = {}
    commits: list[Commit] = []

    def commit(when: str, author: str, message: str, **changes: str) -> None:
        ops = []
        for path, text in changes.items():
            path = {"profile": PROFILE, "lint": ".github/workflows/lint.yml",
                    "mdl": ".markdownlint.yaml", "readme": "README.md",
                    "catalog": "catalog-info.yaml", "codeowners": ".github/CODEOWNERS"}[path]
            if files.get(path) != text:
                ops.append(Write(path, text))
                files[path] = text
        assert ops, message
        commits.append(Commit(when, author, message, tuple(ops)))

    commit("2023-03-14 10:00", "erik.lindqvist",
           "docs: member-only organisation profile\n\n"
           "One page for new joiners and for anyone looking for an owner: tribes,\n"
           "squads, how we work and where things live.",
           readme=README, profile=PROFILE_VERSIONS.at(None), catalog=CATALOG_INFO,
           codeowners=CODEOWNERS)
    commit("2023-09-05 14:20", "fatima.benali",
           "ci: markdownlint on pull requests",
           lint=LINT_WORKFLOW.format(version="v11"), mdl=MARKDOWNLINT)
    commit("2024-05-14 09:00", "platform-bot",
           "chore(deps): bump DavidAnson/markdownlint-cli2-action from 11 to 16",
           lint=LINT_WORKFLOW.format(version="v16"))
    commit("2024-10-15 15:30", "lena.fischer",
           "docs(profile): golden path for cards schema changes\n\n"
           "Every cards repo calls schema-compat from cards-ci-workflows since\n"
           "INC-2024-09-12-003.",
           profile=PROFILE_VERSIONS.at("schema-compat"))
    commit("2025-01-20 10:15", "erik.lindqvist",
           "docs(profile): Lenses and Datadog replace Control Center and Grafana",
           profile=PROFILE_VERSIONS.at("lenses-datadog"))
    commit("2025-02-17 10:40", "erik.lindqvist",
           "docs(profile): on-call moves to PagerDuty",
           profile=PROFILE_VERSIONS.at("pagerduty"))
    commit("2025-06-10 14:00", "fatima.benali",
           "docs(profile): main repositories per squad, java-build golden path\n\n"
           "The question we get most in #platform-engineering is \"who owns X?\".",
           profile=PROFILE_VERSIONS.at("repos"))
    commit("2026-03-03 11:20", "lena.fischer",
           "docs(profile): checklist for new joiners",
           profile=PROFILE_VERSIONS.at("new-joiners"))

    assert files[PROFILE] == PROFILE_VERSIONS.final
    return tuple(commits)


HISTORY = _build_history()


REPO_SPEC = RepoSpec(
    name=REPO,
    description="DSS26 Bank Engineering - the member-only organisation profile.",
    team="platform-engineering",
    domain="platform",
    tier="C",
    topics=("documentation", "onboarding", "team-platform-engineering"),
    history=HISTORY,
    labels=DEFAULT_LABELS,
    team_access=(("cards-platform", "push"),),
)
