"""Forensics sub-agent - finds the culprit change via the GitHub MCP.

The prompt names only the GitHub organisation; which repo and PR are to blame
is discovered with an org-wide search of the PRs merged in the incident
window. The supervisor runs it alongside diagnosis, so its brief carries
triage's identifiers rather than diagnosis' findings. A
:class:`~agent.tool_budget.ToolBudget` caps its calls, because when the
culprit is not on GitHub the model would otherwise keep looking. When
``has_github`` is False the prompt switches to a "GitHub unavailable -
return null, don't speculate" branch.
"""

from __future__ import annotations

from strands import Agent

from agent.config import FORENSICS_MODEL, FORENSICS_TOOL_BUDGET, GITHUB_ORG
from agent.models import build_model
from agent.prompts import load_prompt
from agent.tool_budget import ToolBudget


def build_forensics_agent(
    tools,
    *,
    has_github: bool = True,
    model: str | None = None,
) -> Agent:
    budget = FORENSICS_TOOL_BUDGET if has_github else 0
    return Agent(
        name="code_forensics_agent",
        model=build_model(model or FORENSICS_MODEL),
        system_prompt=load_prompt(
            "forensics",
            MCP_GITHUB=has_github,
            NO_GITHUB=not has_github,
            GITHUB_ORG=GITHUB_ORG,
        ),
        tools=tools,
        hooks=[ToolBudget(budget)] if budget > 0 else [],
    )
