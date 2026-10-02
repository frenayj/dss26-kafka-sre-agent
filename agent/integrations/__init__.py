"""Live vendor clients behind the agent's MCP servers (:mod:`agent.mcp_servers`).

Each module here speaks one vendor's real API and returns payloads in the
SAME shape the corresponding fixture back-end emits. That symmetry is the
whole design: the MCP tool contract (names, arguments, JSON shape) is a fixed
surface the sub-agent prompts and the UI are written against, and swapping
fixtures for a real API must not move it.

So the boundary is drawn here, not at the tool: a live module's job is to
translate the vendor's wire format into our contract, and to fail loudly when
it cannot. It never falls back to fixtures - a run that silently serves
canned data while claiming to be live is worse than a run that errors.
"""

from __future__ import annotations


class IntegrationError(RuntimeError):
    """A live back-end could not serve a request.

    Raised for missing credentials, auth failures, and upstream errors alike.
    The MCP tool catches this and returns it to the model as a structured
    error payload, so the agent can say "PagerDuty is unreachable" instead of
    inventing an incident.
    """

    def __init__(self, message: str, *, system: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.system = system
        self.hint = hint

    def as_payload(self) -> dict:
        """Render as the error dict the MCP tools return to the model."""
        payload = {"error": str(self), "system": self.system, "mode": "live"}
        if self.hint:
            payload["hint"] = self.hint
        return payload
