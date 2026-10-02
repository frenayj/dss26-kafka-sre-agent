"""Triage sub-agent - turns a PagerDuty incident into structured facts.

The ``has_pagerduty`` flag toggles between two prompt branches: tool-driven
(call ``get_incident``) and parse-the-JSON-directly (no MCP tools available).
``has_kb`` adds the Confluence read tools: open the alert's runbook and look
up the service page and similar past incidents. ``pagerduty_live`` swaps the
stub's tools for PagerDuty's hosted MCP server - different tool names, and
triage acknowledges the incident and leaves a note, under
:class:`~agent.pagerduty_guard.PagerDutyWritePolicy`.
"""

from __future__ import annotations

from strands import Agent

from agent.config import TRIAGE_MODEL
from agent.models import build_model
from agent.pagerduty_guard import PagerDutyWritePolicy
from agent.prompts import load_prompt


def build_triage_agent(
    tools,
    *,
    has_pagerduty: bool = True,
    pagerduty_live: bool = False,
    has_kb: bool = False,
    model: str | None = None,
) -> Agent:
    return Agent(
        name="triage_agent",
        model=build_model(model or TRIAGE_MODEL),
        system_prompt=load_prompt(
            "triage",
            PAGERDUTY_STUB=has_pagerduty and not pagerduty_live,
            PAGERDUTY_LIVE=has_pagerduty and pagerduty_live,
            NO_PAGERDUTY=not has_pagerduty,
            KB=has_kb,
        ),
        tools=tools,
        hooks=[PagerDutyWritePolicy()] if has_pagerduty and pagerduty_live else [],
    )
