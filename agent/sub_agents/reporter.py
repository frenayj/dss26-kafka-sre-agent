"""Reporter sub-agent - writes the Confluence RCA and posts the Slack summary.

Both publishers are independently toggleable: ``has_confluence`` /
``has_slack``. When both are off the prompt switches to "produce the RCA
inline as your final response" mode so the supervisor still gets a useful
write-up. ``pagerduty_notes`` (live PagerDuty only) hands it the PagerDuty
MCP tools to leave a closing note on the incident, under
:class:`~agent.pagerduty_guard.PagerDutyWritePolicy`.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from strands import Agent
from strands.hooks import HookProvider

from agent.config import REPORTER_MODEL, SLACK_DEFAULT_CHANNEL
from agent.models import build_model
from agent.pagerduty_guard import PagerDutyWritePolicy
from agent.prompts import load_prompt

# The reporter's create_page argument IS the RCA, which makes it the longest
# reply any role writes. The prompt asks for under 900 words; the cap leaves
# headroom, because a reply that hits it is cut off mid-call
# (MaxTokensReachedException) and nothing gets published.
REPORTER_MAX_TOKENS = 16384


def slack_channel() -> str:
    """The channel the reporter is told to post to.

    SLACK_DEFAULT_CHANNEL pins every post anyway (see
    agent/integrations/slack.py); asking for it up front means the post is
    never redirected, so there is no override for the summary to fret about.
    """
    channel = SLACK_DEFAULT_CHANNEL.strip()
    if not channel:
        return "#sre-oncall"
    if re.fullmatch(r"[CGD][A-Z0-9]{8,}", channel):  # a channel id, not a name
        return channel
    return "#" + channel.lstrip("#")


def build_reporter_agent(
    tools,
    *,
    has_confluence: bool = True,
    has_kb: bool = False,
    has_slack: bool = True,
    pagerduty_notes: bool = False,
    skills_plugin: Optional[HookProvider] = None,
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
        name="reporter_agent",
        model=build_model(model or REPORTER_MODEL, max_tokens=REPORTER_MAX_TOKENS),
        system_prompt=load_prompt(
            "reporter",
            MCP_CONFLUENCE=has_confluence,
            NO_CONFLUENCE=not has_confluence,
            KB=has_kb,
            MCP_SLACK=has_slack,
            SLACK_CHANNEL=slack_channel(),
            NO_PUBLISHING=not (has_confluence or has_slack),
            PAGERDUTY_LIVE=pagerduty_notes,
            # Slack and the PagerDuty note both wait on the page URL, then
            # go out together.
            FOLLOW_UPS=has_confluence and (has_slack or pagerduty_notes),
            SKILLS=skills_active,
            SKILL_NAMES=skill_names_block,
        ),
        tools=tools,
        plugins=plugins,
        hooks=[PagerDutyWritePolicy()] if pagerduty_notes else [],
    )
