"""System prompts, stored as Markdown files and loaded at agent construction.

Keeping prompts out of Python source makes them readable and reviewable as
content. The loader supports a tiny template syntax so one prompt file can
adapt to the skills and MCP servers enabled for a run:

  ``{% if FLAG %}...{% endif %}``
      Kept if ``ctx[FLAG]`` is truthy, otherwise dropped. Flags are
      upper-snake-case; blocks may nest; there is no ``else`` (pass a negated
      flag such as ``NO_GITHUB`` instead).

  ``{{ VAR }}``
      Replaced with ``str(ctx[VAR])`` (empty string if absent).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

_PROMPTS_DIR = Path(__file__).parent

# An innermost if-block: one whose body contains no other `{% if`. Nested
# blocks collapse bottom-up by re-running the substitution until stable.
_IF_BLOCK_RE = re.compile(
    r"{%\s*if\s+([A-Z_][A-Z0-9_]*)\s*%}"
    r"((?:(?!{%\s*if\s+|{%\s*endif\s*%}).)*?)"
    r"{%\s*endif\s*%}",
    re.DOTALL,
)
_VAR_RE = re.compile(r"{{\s*([A-Z_][A-Z0-9_]*)\s*}}")


def _render(template: str, ctx: Mapping[str, Any]) -> str:
    """Expand conditional blocks, then variables; collapse blank runs."""
    text = template
    # Bounded, so a malformed template cannot spin forever.
    for _ in range(50):
        new_text = _IF_BLOCK_RE.sub(lambda m: m.group(2) if ctx.get(m.group(1)) else "", text)
        if new_text == text:
            break
        text = new_text

    text = _VAR_RE.sub(lambda m: str(ctx.get(m.group(1), "")), text)
    # Avoid a paragraph-sized gap where a block used to be.
    return re.sub(r"\n{3,}", "\n\n", text)


def load_prompt(name: str, **ctx: Any) -> str:
    """Read ``agent/prompts/<name>.md``, rendered with ``ctx`` when given.

    Example::

        load_prompt("triage", MCP_PAGERDUTY=True)
    """
    raw = (_PROMPTS_DIR / f"{name}.md").read_text()
    return raw if not ctx else _render(raw, ctx)
