"""Forensics runs on a short leash, in parallel with diagnosis.

The tool budget is what keeps a run bounded when the culprit is not on GitHub
(the model would otherwise keep browsing), and the prompts are what make the
supervisor fan diagnosis and forensics out in one turn.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.prompts import load_prompt
from agent.tool_budget import ToolBudget


def _call(name="search_pull_requests"):
    return SimpleNamespace(tool_use={"name": name, "input": {}}, cancel_tool=False)


def test_calls_within_the_budget_go_through():
    budget = ToolBudget(3)
    calls = [_call() for _ in range(3)]
    for call in calls:
        budget._check(call)
    assert not any(c.cancel_tool for c in calls)


def test_calls_past_the_budget_are_cancelled_with_a_way_forward():
    budget = ToolBudget(2)
    calls = [_call() for _ in range(4)]
    for call in calls:
        budget._check(call)
    assert [bool(c.cancel_tool) for c in calls] == [False, False, True, True]
    assert "write your finding now" in calls[2].cancel_tool


def test_each_invocation_gets_a_fresh_budget():
    """A supervisor follow-up call to forensics must not start out of budget."""
    budget = ToolBudget(1)
    budget._check(_call())
    budget._reset(SimpleNamespace())
    second = _call()
    budget._check(second)
    assert not second.cancel_tool


def test_forensics_agent_carries_the_budget_only_with_github(monkeypatch):
    forensics = pytest.importorskip("agent.sub_agents.forensics")
    built = []

    class Recording(ToolBudget):
        def __init__(self, limit):
            super().__init__(limit)
            built.append(limit)

    monkeypatch.setattr(forensics, "ToolBudget", Recording)
    monkeypatch.setattr(forensics, "FORENSICS_TOOL_BUDGET", 9)
    forensics.build_forensics_agent([], has_github=True, model="claude")
    forensics.build_forensics_agent([], has_github=False, model="claude")
    assert built == [9]

    monkeypatch.setattr(forensics, "FORENSICS_TOOL_BUDGET", 0)  # 0 disables the cap
    forensics.build_forensics_agent([], has_github=True, model="claude")
    assert built == [9]


def test_forensics_prompt_is_a_narrow_brief():
    prompt = load_prompt("forensics", MCP_GITHUB=True, NO_GITHUB=False, GITHUB_ORG="dss26-org")
    assert "org:dss26-org is:pr is:merged merged:>=" in prompt
    assert "at most three" in prompt
    assert "Do not browse directories" in prompt
    # It runs before diagnosis has returned, so it must not wait for one.
    assert "at the same time as" in prompt


def test_supervisor_fans_out_diagnosis_and_forensics():
    prompt = load_prompt("supervisor", PAGERDUTY=True, NO_PAGERDUTY=False)
    assert "in the same turn" in prompt
    assert "created_at" in prompt


@pytest.mark.parametrize("has_pd, says", [(True, "incident id and its title only"),
                                          (False, "the incident payload as")])
def test_supervisor_only_copies_the_payload_when_triage_cannot_fetch_it(has_pd, says):
    prompt = load_prompt("supervisor", PAGERDUTY=has_pd, NO_PAGERDUTY=not has_pd)
    assert says in prompt
    assert "at most 150 words" in prompt


def test_reporter_writes_a_short_page_and_publishes_follow_ups_together():
    flags = dict(MCP_CONFLUENCE=True, NO_CONFLUENCE=False, KB=True, MCP_SLACK=True,
                 NO_SLACK=False, NO_PUBLISHING=False, PAGERDUTY_LIVE=True, SKILLS=False,
                 SKILL_NAMES="")
    prompt = load_prompt("reporter", FOLLOW_UPS=True, **flags)
    assert "Appendix" not in prompt
    assert "under 900 words" in prompt
    assert "make the remaining calls below" in prompt
    assert "make the remaining calls below" not in load_prompt("reporter", FOLLOW_UPS=False, **flags)


def test_the_reporter_gets_the_specialists_outputs_verbatim():
    supervisor = pytest.importorskip("agent.sub_agents.supervisor")
    findings = {
        "code_forensics_agent": "PR #4 in dss26-org/merchant-gateway",
        "triage_agent": '{"incident_id": "Q1"}',
        "reporter_agent": "never attached",
    }
    case = supervisor.compose_case_file("  Likely PR #4.  ", findings)
    assert case.startswith("## Incident commander's verdict\n\nLikely PR #4.")
    # Case-file order, verbatim, and only the specialists.
    assert case.index('{"incident_id": "Q1"}') < case.index("PR #4 in dss26-org")
    assert "Kafka diagnosis" not in case  # not run yet: no empty section
    assert "never attached" not in case
