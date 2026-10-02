"""Data model for the DSS26 Bank GitHub estate (the ``dss26-org`` org).

Everything the seeder pushes and every pull request the scenario engine opens
is declared as data in this package, so the history the agent reads on GitHub
is reproducible: ``seed.py --rebuild`` deletes the repos and replays the same
commits, with the same authors and the same backdated timestamps.

Three kinds of change, matching what GitHub can and cannot fake:

* :class:`Commit` - a backdated commit in a repo's history. Git lets us set
  author and committer dates freely, so the history reaches back to 2022 and
  lines up with the ADRs and postmortems in the Confluence space.
* :class:`ScenarioPR` - a pull request opened and merged *now* by the
  scenario engine. GitHub stamps PRs with wall-clock time and offers no way to
  backdate them, so the PRs that must sit close to an incident (the culprit
  and the decoys merged the same day) are created live, not seeded.
* An ``open`` :class:`ScenarioPR` is created at seed time and left open - for
  example the consumer-side change that should have landed first.

File contents are either inline strings or files under ``files/<repo>/``.
Edits are exact, single-occurrence string replacements: a replay fails loudly
if an edit no longer applies, instead of producing a history that silently
differs from the one the demo story describes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from zoneinfo import ZoneInfo

ORG = os.environ.get("GITHUB_ORG", "").strip() or "dss26-org"

# Reserved TLD (RFC 2606): no real GitHub account can verify an address here,
# so persona commits never get linked to a stranger's profile and avatar.
EMAIL_DOMAIN = "dss26bank.example"

# The bank's engineering hub. Commit timestamps carry this offset (CET/CEST),
# which is what a real European bank's history looks like.
TZ = ZoneInfo("Europe/Paris")

PACKAGE_ROOT = Path(__file__).resolve().parent
FILES_ROOT = PACKAGE_ROOT / "files"
REPO_ROOT = PACKAGE_ROOT.parent.parent


# ---------------------------------------------------------------------------
# People and teams
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Person:
    login: str
    name: str
    team: str
    title: str
    joined: str  # YYYY-MM-DD - no commits before this date
    left: Optional[str] = None  # YYYY-MM-DD - no commits after this date

    @property
    def email(self) -> str:
        return f"{self.login}@{EMAIL_DOMAIN}"


@dataclass(frozen=True)
class Team:
    slug: str
    name: str
    description: str
    parent: Optional[str] = None


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Write:
    """Create or overwrite a file. Exactly one of ``content`` / ``src``."""

    path: str
    content: Optional[str] = None
    src: Optional[str] = None  # relative to FILES_ROOT
    executable: bool = False

    def text(self) -> str:
        if (self.content is None) == (self.src is None):
            raise ValueError(f"Write({self.path}): pass exactly one of content/src")
        if self.content is not None:
            return self.content
        return (FILES_ROOT / self.src).read_text()


@dataclass(frozen=True)
class Edit:
    """Replace exactly one occurrence of ``old`` with ``new``."""

    path: str
    old: str
    new: str


@dataclass(frozen=True)
class Delete:
    path: str


Op = Union[Write, Edit, Delete]


class ReplayError(RuntimeError):
    """An op does not apply to the tree it was written against."""


def apply_edit(text: str, op: Edit, where: str) -> str:
    count = text.count(op.old)
    if count != 1:
        raise ReplayError(
            f"{where}: Edit({op.path}) expected exactly 1 match of "
            f"{op.old[:60]!r}, found {count}"
        )
    return text.replace(op.old, op.new, 1)


def apply_ops(root: Path, ops: tuple[Op, ...], where: str) -> None:
    """Apply ops to a working tree on disk."""
    for op in ops:
        target = root / op.path
        if isinstance(op, Write):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(op.text())
            if op.executable:
                target.chmod(0o755)
        elif isinstance(op, Edit):
            if not target.exists():
                raise ReplayError(f"{where}: Edit({op.path}) on a missing file")
            target.write_text(apply_edit(target.read_text(), op, where))
        elif isinstance(op, Delete):
            if not target.exists():
                raise ReplayError(f"{where}: Delete({op.path}) on a missing file")
            target.unlink()
        else:  # pragma: no cover - type guard
            raise TypeError(op)


# ---------------------------------------------------------------------------
# History and scenario pull requests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Commit:
    when: str  # "YYYY-MM-DD HH:MM" in Europe/Paris local time
    author: str  # Person.login
    message: str
    ops: tuple[Op, ...]

    def timestamp(self) -> datetime:
        return datetime.strptime(self.when, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


# kind:
#   "decoy"   - merged the day of the demo by ``scenario.py warmup``; plausible
#               suspects the agent has to rule out.
#   "culprit" - merged by ``scenario.py culprit <scenario>`` from the induce
#               scripts, minutes before the incident fires.
#   "open"    - opened at seed time and never merged.
PR_KINDS = ("decoy", "culprit", "open")
SCENARIOS = ("consumer-lag",)


@dataclass(frozen=True)
class ScenarioPR:
    key: str  # stable id, unique across the org
    kind: str
    scenario: Optional[str]  # one of SCENARIOS, or None for org-wide noise
    branch: str
    title: str
    body: str
    author: str  # Person.login - author of the PR's commit
    commit_message: str
    # Edits only for decoys and culprits: an Edit is invertible, which is what
    # lets ``scenario.py revert`` produce a real revert commit and lets the
    # engine detect from the file contents whether a PR is already applied.
    ops: tuple[Op, ...]
    labels: tuple[str, ...] = ()
    # Who authors the revert commit when ``make reset`` rolls a culprit back.
    revert_author: Optional[str] = None
    revert_body: str = ""

    def __post_init__(self) -> None:
        if self.kind not in PR_KINDS:
            raise ValueError(f"{self.key}: unknown kind {self.kind!r}")
        if self.scenario is not None and self.scenario not in SCENARIOS:
            raise ValueError(f"{self.key}: unknown scenario {self.scenario!r}")
        if self.kind in ("decoy", "culprit") and not all(
            isinstance(op, Edit) for op in self.ops
        ):
            raise ValueError(f"{self.key}: decoys and culprits must be Edit-only")


@dataclass(frozen=True)
class Label:
    name: str
    color: str  # hex, no '#'
    description: str = ""


@dataclass(frozen=True)
class RepoSpec:
    name: str
    description: str
    team: str  # owning Team.slug (gets 'maintain')
    domain: str
    # "A" story-critical (culprit or decoy lives here), "B" neighbour that shows
    # up in code search for the incident's assets, "C" backdrop.
    tier: str
    topics: tuple[str, ...]
    history: tuple[Commit, ...]
    prs: tuple[ScenarioPR, ...] = ()
    labels: tuple[Label, ...] = ()
    # Extra team grants beyond the owner, e.g. (("platform-engineering", "push"),).
    team_access: tuple[tuple[str, str], ...] = ()
    # Reusable-workflow repos must be callable from the rest of the org.
    actions_access_org: bool = False

    def __post_init__(self) -> None:
        if self.tier not in ("A", "B", "C"):
            raise ValueError(f"{self.name}: tier must be A/B/C")
        stamps = [c.timestamp() for c in self.history]
        if stamps != sorted(stamps):
            raise ValueError(f"{self.name}: history is not in chronological order")


DEFAULT_LABELS: tuple[Label, ...] = (
    Label("bug", "d73a4a", "Something isn't working"),
    Label("dependencies", "0366d6", "Dependency updates"),
    Label("docs", "0075ca", "Documentation only"),
    Label("ci", "ededed", "Build and CI pipeline"),
    Label("tier-1", "b60205", "Touches a Tier-1 card flow - needs a CAB ticket"),
)
