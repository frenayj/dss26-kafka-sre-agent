"""Diagnosis sub-agent - drives the Lenses MCP + Kafka skills.

This is the heaviest sub-agent: its system prompt plus the (sorted) Lenses
MCP tool list make up a large, stable prefix on every turn.

The prompt branches on three flags computed by the supervisor factory:

* ``has_lenses`` - the Lenses MCP server is reachable
* ``skills_plugin`` - when None, no skills are wired into the agent at all
* ``enabled_skill_names`` - the names displayed in the prompt's
  <available_skills> section preview

When both ``has_lenses`` is False and ``skills_plugin`` is None the prompt
flips to a degraded mode that asks for a best-guess hypothesis from the
triage payload alone.
"""

from __future__ import annotations

from typing import Iterable, Optional

from strands import Agent
from strands.hooks import HookProvider

from agent.config import DIAGNOSIS_MODEL
from agent.models import build_model
from agent.prompts import load_prompt


def build_diagnosis_agent(
    tools,
    *,
    skills_plugin: Optional[HookProvider] = None,
    has_lenses: bool = True,
    enabled_skill_names: Iterable[str] = (),
    model: str | None = None,
) -> Agent:
    plugins = [skills_plugin] if skills_plugin is not None else []
    skills_active = skills_plugin is not None
    skill_names_block = (
        "\n".join(f"  - {n}" for n in enabled_skill_names)
        if skills_active and enabled_skill_names
        else ""
    )

    return Agent(
        name="kafka_diagnosis_agent",
        model=build_model(model or DIAGNOSIS_MODEL),
        system_prompt=load_prompt(
            "diagnosis",
            MCP_LENSES=has_lenses,
            SKILLS=skills_active,
            SKILL_NAMES=skill_names_block,
            NO_DIAGNOSIS_TOOLS=not (has_lenses or skills_active),
        ),
        tools=tools,
        plugins=plugins,
    )
