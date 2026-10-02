"""Skill discovery - single source of truth for what's available.

Walks ``SKILLS_DIR`` (``agent/skills/``), reads each ``SKILL.md``'s YAML
frontmatter, and returns one :class:`SkillInfo` per skill. Used by:

* ``GET /skills`` on the FastAPI server, to populate the toggle UI.
* The supervisor factory in :mod:`agent.runner`, to resolve user-enabled
  skill *names* (e.g. ``kafka-consumer-lag``) back to filesystem paths the
  ``AgentSkills`` plugin can load.

We deliberately don't depend on PyYAML - Strands' bundled YAML parser
suffices, and the only fields we need (``name``, ``description``) are
trivially parseable. Anything else stays in the frontmatter and is
re-exposed via the plugin itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from agent.config import SKILLS_DIR

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
# Tolerate quoted, unquoted, single-quoted descriptions.
_NAME_RE = re.compile(r'^name:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)
_DESCRIPTION_RE = re.compile(r'^description:\s*"?(.+?)"?\s*$', re.MULTILINE)


@dataclass(frozen=True)
class SkillInfo:
    """One on-disk skill, identified by directory name."""

    name: str
    description: str
    path: Path

    def as_dict(self) -> Dict[str, str]:
        return {"name": self.name, "description": self.description}


def _parse_frontmatter(text: str) -> tuple[str | None, str | None]:
    """Return ``(name, description)`` extracted from a SKILL.md's frontmatter."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, None
    block = m.group(1)
    name_m = _NAME_RE.search(block)
    desc_m = _DESCRIPTION_RE.search(block)
    return (
        name_m.group(1).strip() if name_m else None,
        desc_m.group(1).strip() if desc_m else None,
    )


def list_available_skills(skills_dir: Path | None = None) -> List[SkillInfo]:
    """Return every subdirectory of ``skills_dir`` that contains a ``SKILL.md``.

    Skills are sorted by name so the UI ordering is stable across restarts.
    """
    base = skills_dir or SKILLS_DIR
    if not base.exists():
        return []

    out: List[SkillInfo] = []
    for entry in sorted(base.iterdir()):
        skill_md = entry / "SKILL.md"
        if not entry.is_dir() or not skill_md.is_file():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        name, description = _parse_frontmatter(text)
        # Fall back to the directory name if the frontmatter didn't carry
        # a `name:` - keeps a malformed SKILL.md from disappearing silently.
        out.append(
            SkillInfo(
                name=name or entry.name,
                description=description or "",
                path=entry,
            )
        )
    return out


def resolve_skill_paths(
    enabled: set[str],
    *,
    skills_dir: Path | None = None,
) -> List[Path]:
    """Map a set of skill *names* to their on-disk directory paths.

    Unknown names are silently dropped - the UI is the trust boundary; the
    server is conservative.
    """
    available = list_available_skills(skills_dir)
    return [s.path for s in available if s.name in enabled]
