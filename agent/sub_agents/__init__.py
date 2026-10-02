"""Per-sub-agent factory functions.

Each module exports a ``build_<name>_agent(tools, ...)`` factory returning a
configured ``strands.Agent``. The factories are pure - they don't enter MCP
context managers or list tools; callers do that and pass the tool lists in.

``supervisor`` is the orchestrator: it wraps the other four agents as
``@tool`` closures and returns the supervisor ``Agent`` that drives the
end-to-end incident response.
"""
