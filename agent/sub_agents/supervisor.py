"""Supervisor agent: wraps the four sub-agents as ``@tool`` closures.

The ``@tool`` wrappers must be closures over the live sub-agent instances:
hoisting them to module scope would require a module-level registry (state-y)
or rebuilding all four agents per call (slow). Build the sub-agents in
``runner.py`` inside the MCP ExitStack, then pass them here.

The supervisor is the incident-commander orchestrator. Like every sub-agent it
gets its model handle from ``agent.models.build_model``, which routes through
the LiteLLM gateway (one OpenAI-compatible endpoint; provider chosen by alias).

Inner observability: the closures are ``async def`` and drain each sub-agent
via ``stream_async``. Every event yielded by a sub-agent is forwarded to the
caller-provided ``asyncio.Queue`` (set via ``current_event_queue`` ContextVar
at the top of a request) so the live-view dashboard can render the inner tool
calls / reasoning / text as nested rows under the supervisor's tool invocation.
When the ContextVar is unset (e.g. the CLI path in ``runner.run()``), the
closures still work - sub-agent events just don't get forwarded, and the
final assistant text is returned synchronously like before.

Handoffs: as each sub-agent starts, a ``handoff`` item goes onto the same
queue ahead of its events - the exact prompt it was handed, plus the rest of
what it starts with (system prompt, tools, model, earlier turns). The
reporter's prompt is composed here rather than written by the supervisor, so
this is the only place the dashboard can see what it really received.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import Optional

from strands import Agent, ToolContext, tool

from agent.config import SUPERVISOR_MODEL
from agent.models import build_model
from agent.prompts import load_prompt

# Set by ``agent/server.py`` for the duration of one /run request. The four
# @tool closures push every event their sub-agent emits onto this queue,
# tagged with the closure's name, so the SSE handler can interleave inner
# events with the supervisor's own events.
current_event_queue: ContextVar[Optional[asyncio.Queue]] = ContextVar(
    "current_event_queue", default=None
)


# The specialists whose findings the reporter writes up, in case-file order.
CASE_FILE_SECTIONS = (
    ("triage_agent", "Triage"),
    ("kafka_diagnosis_agent", "Kafka diagnosis"),
    ("code_forensics_agent", "Code forensics"),
)


def compose_case_file(verdict: str, findings: dict[str, str]) -> str:
    """The reporter's input: the supervisor's verdict, then each specialist's output.

    The supervisor writes only its verdict; the specialists' outputs are
    attached verbatim. Nothing is lost or paraphrased on the way, and the
    supervisor doesn't spend output tokens re-typing text it can hand over.
    """
    parts = [f"## Incident commander's verdict\n\n{verdict.strip()}"]
    for source, label in CASE_FILE_SECTIONS:
        if findings.get(source):
            parts.append(f"## {label} ({source} output)\n\n{findings[source].strip()}")
    return "\n\n".join(parts)


def agent_context(
    agent: Agent,
    prompt: str,
    *,
    call_id: str | None = None,
    prior_messages: int = 0,
) -> dict:
    """What ``agent`` starts a call with: the payload of a ``handoff`` frame.

    ``call_id`` is the supervisor's tool call that started it (namespaced like
    the dashboard's tool ids), None for the supervisor itself.
    ``prior_messages`` counts the turns it already holds from earlier calls in
    the run - sub-agents are built once per run, so a second call to one
    carries its first conversation.
    """
    return {
        "callId": call_id,
        "prompt": prompt,
        "systemPrompt": agent.system_prompt or "",
        "tools": list(agent.tool_names),
        "model": agent.model.get_config().get("model_id"),
        "priorMessages": prior_messages,
    }


def build_supervisor(
    *,
    triage: Agent,
    diagnosis: Agent,
    forensics: Agent,
    reporter: Agent,
    model: str | None = None,
    has_pagerduty: bool = True,
) -> Agent:
    """Wrap the four specialist agents as async tools and return the supervisor.

    ``has_pagerduty`` tells the prompt whether triage can fetch the incident
    itself (so the supervisor passes only its id) or needs the payload.
    """

    # Each specialist's latest output, attached to the reporter's case file.
    findings: dict[str, str] = {}

    async def _run_subagent(
        source: str, sub_agent: Agent, prompt: str, context: ToolContext
    ) -> str:
        """Stream a sub-agent and forward every event onto the request queue.

        Returns the sub-agent's final assistant text - that's what becomes
        the tool's return value the supervisor sees in the next turn.
        """
        call_id = f"supervisor:{context.tool_use['toolUseId']}"
        output = await _stream_subagent(source, sub_agent, prompt, call_id)
        findings[source] = output
        return output

    async def _stream_subagent(
        source: str, sub_agent: Agent, prompt: str, call_id: str
    ) -> str:
        queue = current_event_queue.get()
        text_parts: list[str] = []
        result_value: Optional[str] = None
        prior_messages = len(sub_agent.messages)
        handed_over = False

        async for event in sub_agent.stream_async(prompt):
            if queue is not None:
                if not handed_over:
                    # Sent on the first event rather than before the call:
                    # the skills plugin appends its catalogue to the system
                    # prompt as the invocation starts.
                    handed_over = True
                    context = agent_context(
                        sub_agent, prompt, call_id=call_id, prior_messages=prior_messages
                    )
                    await queue.put((source, {"handoff": context}))
                # Single-loop asyncio.Queue - safe because Strands runs the
                # async tool in the same loop as the supervisor.stream_async
                # caller (the /run handler).
                await queue.put((source, event))

            if isinstance(event, dict):
                data = event.get("data")
                if data:
                    text_parts.append(str(data))
                if event.get("complete") or event.get("force_stop"):
                    result = event.get("result")
                    if result is not None:
                        result_value = str(result)
                    break

        # Prefer the explicit final result Strands gives us; fall back to
        # accumulated text deltas; never return empty (would confuse the
        # supervisor's next turn).
        if result_value:
            return result_value
        if text_parts:
            return "".join(text_parts)
        return "(sub-agent returned no output)"

    @tool(context=True)
    async def triage_agent(incident_json: str, tool_context: ToolContext) -> str:
        """Run the triage specialist over a PagerDuty incident.

        Args:
            incident_json: The incident id and title when PagerDuty is
                connected (triage fetches the rest itself); otherwise the
                raw JSON of the incident.

        Returns:
            Structured triage facts: cluster, consumer group, service,
            severity, summary - plus the team knowledge-base pages it read
            (runbook, service page, past incidents), when Confluence is on.
        """
        return await _run_subagent("triage_agent", triage, incident_json, tool_context)

    @tool(context=True)
    async def kafka_diagnosis_agent(triage_summary: str, tool_context: ToolContext) -> str:
        """Diagnose the Kafka issue using Lenses MCP + Kafka skills.

        Runs in parallel with ``code_forensics_agent`` - call both in the
        same turn once triage has returned.

        Args:
            triage_summary: The identifiers from ``triage_agent`` - must
                include cluster + consumer group (or connector) - plus any
                hypotheses from team pages, labelled as such.

        Returns:
            Structured diagnosis with cluster comparison, lag pattern,
            most likely root cause, and whether a recent change is
            implicated.
        """
        return await _run_subagent("kafka_diagnosis_agent", diagnosis, triage_summary, tool_context)

    @tool(context=True)
    async def code_forensics_agent(brief: str, tool_context: ToolContext) -> str:
        """Find the merged PR most likely responsible for the incident.

        Runs in parallel with ``kafka_diagnosis_agent`` - call both in the
        same turn once triage has returned.

        Args:
            brief: The failing identifiers from triage (topic, schema
                subject, consumer group, connector, service, repo if known),
                the services a team page says produce or consume them, and
                the incident's start time. On a follow-up call, add the
                diagnosis' specific finding.

        Returns:
            A structured finding with repo, PR number, title, authors, the
            exact change and the symptom it would cause, and the candidates
            it ruled out.
        """
        return await _run_subagent("code_forensics_agent", forensics, brief, tool_context)

    @tool(context=True)
    async def reporter_agent(case_file: str, tool_context: ToolContext) -> str:
        """Write the Confluence RCA and post the Slack summary.

        The triage, diagnosis and forensics outputs are attached to the
        reporter's input automatically - do not repeat them.

        Args:
            case_file: Your verdict only, at most 150 words: the root cause
                you conclude and how confident, which findings agree or
                conflict, and what you ruled out.

        Returns:
            Confirmation including the Confluence page URL and the Slack
            channel acknowledgement.
        """
        return await _run_subagent(
            "reporter_agent", reporter, compose_case_file(case_file, findings), tool_context
        )

    return Agent(
        name="supervisor",
        model=build_model(model or SUPERVISOR_MODEL),
        system_prompt=load_prompt(
            "supervisor",
            PAGERDUTY=has_pagerduty,
            NO_PAGERDUTY=not has_pagerduty,
        ),
        tools=[
            triage_agent,
            kafka_diagnosis_agent,
            code_forensics_agent,
            reporter_agent,
        ],
    )
