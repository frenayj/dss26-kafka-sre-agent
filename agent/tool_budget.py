"""A hard cap on how many tool calls one sub-agent invocation may make.

A prompt can ask for a short investigation; it cannot guarantee one. When the
evidence is not where the method expects it - no culprit PR in the window,
say - a model keeps looking, and a demo run that should take four minutes
takes twelve. This hook counts calls per invocation and, past the cap,
cancels each further call with a message telling the model to write up what
it has. The model sees that as a tool error and answers on its next turn.

The count resets at the start of every invocation, so a supervisor's
follow-up call to the same sub-agent gets a fresh budget.
"""

from __future__ import annotations

from typing import Any

from strands.hooks import BeforeInvocationEvent, BeforeToolCallEvent, HookProvider, HookRegistry


class ToolBudget(HookProvider):
    """Cancel every tool call after the first ``limit`` in one invocation."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self._reset)
        registry.add_callback(BeforeToolCallEvent, self._check)

    def _reset(self, _event: BeforeInvocationEvent) -> None:
        self.used = 0

    def _check(self, event: BeforeToolCallEvent) -> None:
        self.used += 1
        if self.used > self.limit:
            event.cancel_tool = (
                f"Tool budget spent ({self.limit} calls). Do not call any more "
                "tools: write your finding now from what you have, and list "
                "what you could not check."
            )
