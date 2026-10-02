"""Write policy for the live PagerDuty MCP: acknowledge and annotate, nothing else.

PagerDuty's hosted MCP server bundles every incident write into one tool,
``manage_incidents``, switched by ``request.action``: create, update (which
covers resolve, reassign, re-urgency and escalate), add_note, add_responders
and start_workflow. The agent's job ends at "acknowledged, with notes" - the
human on call decides when an incident is resolved and who else gets paged.
A tool filter cannot express that (it is one tool), so this hook inspects each
call and cancels the rest before they reach PagerDuty.

The model sees the cancellation as a tool error with the reason, so it can
carry on with the run rather than retrying blindly.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

WRITE_TOOL = "manage_incidents"

# ``update`` fields other than ``incident_ids`` and ``status`` - any of them set
# means a reassignment, urgency change or escalation, all left to the human.
_UPDATE_FIELDS_DENIED = ("assignment", "urgency", "escalation_level")


def blocked_reason(tool_input: Any) -> Optional[str]:
    """Return why a ``manage_incidents`` call is refused, or None to allow it."""
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            return "manage_incidents input is not valid JSON"
    request = (tool_input or {}).get("request") if isinstance(tool_input, dict) else None
    if isinstance(request, str):
        try:
            request = json.loads(request)
        except ValueError:
            return "manage_incidents request is not valid JSON"
    if not isinstance(request, dict):
        return "manage_incidents needs a request object with an action"

    action = request.get("action")
    if action == "add_note":
        return None
    if action == "update":
        manage = request.get("manage_request") or {}
        if manage.get("status") != "acknowledged":
            return (
                "only status 'acknowledged' is allowed - resolving an incident "
                "is the on-call human's decision"
            )
        changed = [f for f in _UPDATE_FIELDS_DENIED if manage.get(f) is not None]
        if changed:
            return f"changing {', '.join(changed)} is left to the on-call human"
        return None
    return (
        f"action {action!r} is not allowed - the agent may only acknowledge "
        "incidents and add notes"
    )


class PagerDutyWritePolicy(HookProvider):
    """Cancel every ``manage_incidents`` call except acknowledge and add_note."""

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self._check)

    def _check(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use.get("name") != WRITE_TOOL:
            return
        reason = blocked_reason(event.tool_use.get("input"))
        if reason:
            event.cancel_tool = f"Blocked by the demo's PagerDuty policy: {reason}."
