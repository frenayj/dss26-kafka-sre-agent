"""Each sub-agent call reports what the agent was handed.

The dashboard shows the context each agent works from: the exact prompt it
received, its system prompt, tools, model and the turns it already holds.
For the reporter the prompt is composed in the @tool closure (the verdict
plus every specialist's output), so the closure is the only place it exists.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Tuple

import pytest

supervisor_mod = pytest.importorskip("agent.sub_agents.supervisor")


class FakeModel:
    def __init__(self, alias: str):
        self.alias = alias

    def get_config(self) -> dict:
        return {"model_id": self.alias}


class FakeSubAgent:
    """Answers with a fixed text and keeps its conversation, like an Agent."""

    def __init__(self, answer: str, alias: str = "claude"):
        self.answer = answer
        self.system_prompt = f"You answer {answer!r}."
        self.tool_names = ["get_page"]
        self.model = FakeModel(alias)
        self.messages: List[dict] = []

    async def stream_async(self, prompt: str):
        self.messages.append({"role": "user", "content": [{"text": prompt}]})
        yield {"init_event_loop": True}
        yield {"data": self.answer}
        self.messages.append({"role": "assistant", "content": [{"text": self.answer}]})
        yield {"complete": True, "result": self.answer}


@pytest.fixture
def team():
    agents = {
        "triage": FakeSubAgent("cluster cards-prod-euw1", alias="claude-haiku"),
        "diagnosis": FakeSubAgent("schema v2 broke the consumer"),
        "forensics": FakeSubAgent("PR #18"),
        "reporter": FakeSubAgent("page published"),
    }
    sup = supervisor_mod.build_supervisor(**agents, model="claude")
    return sup, agents


def _call(sup: Any, name: str, tool_use_id: str, **kwargs) -> List[Tuple[str, Any]]:
    """Run one supervisor tool as Strands would and collect the queued items."""

    async def go():
        queue: asyncio.Queue = asyncio.Queue()
        token = supervisor_mod.current_event_queue.set(queue)
        try:
            tool = sup.tool_registry.registry[name]
            tool_use = {"toolUseId": tool_use_id, "name": name, "input": kwargs}
            async for _ in tool.stream(tool_use, {"agent": sup}):
                pass
        finally:
            supervisor_mod.current_event_queue.reset(token)
        items = []
        while not queue.empty():
            items.append(queue.get_nowait())
        return items

    return asyncio.run(go())


def _handoffs(items):
    return [(src, ev["handoff"]) for src, ev in items if isinstance(ev, dict) and "handoff" in ev]


def test_a_sub_agent_reports_its_prompt_and_context_before_its_events(team):
    sup, _ = team
    items = _call(sup, "triage_agent", "t1", incident_json='{"id": "Q1"}')

    source, first = items[0]
    assert source == "triage_agent" and "handoff" in first
    handoff = first["handoff"]
    assert handoff["callId"] == "supervisor:t1"
    assert handoff["prompt"] == '{"id": "Q1"}'
    assert handoff["systemPrompt"] == "You answer 'cluster cards-prod-euw1'."
    assert handoff["tools"] == ["get_page"]
    assert handoff["model"] == "claude-haiku"
    assert handoff["priorMessages"] == 0
    assert len(_handoffs(items)) == 1


def test_the_reporter_handoff_is_the_whole_case_file(team):
    sup, _ = team
    _call(sup, "triage_agent", "t1", incident_json="Q1")
    _call(sup, "kafka_diagnosis_agent", "d1", triage_summary="cards-prod-euw1")
    _call(sup, "code_forensics_agent", "f1", brief="topic x")
    items = _call(sup, "reporter_agent", "r1", case_file="PR #18 did it.")

    [(source, handoff)] = _handoffs(items)
    assert source == "reporter_agent"
    prompt = handoff["prompt"]
    assert prompt.startswith("## Incident commander's verdict\n\nPR #18 did it.")
    for finding in ("cluster cards-prod-euw1", "schema v2 broke the consumer", "PR #18"):
        assert finding in prompt


def test_a_follow_up_call_reports_the_turns_the_agent_already_holds(team):
    sup, _ = team
    _call(sup, "code_forensics_agent", "f1", brief="first")
    items = _call(sup, "code_forensics_agent", "f2", brief="second, with the finding")

    [(_, handoff)] = _handoffs(items)
    assert handoff["callId"] == "supervisor:f2"
    assert handoff["priorMessages"] == 2
