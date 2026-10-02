"""Runner - composes MCP clients, sub-agents and the supervisor.

The transport-independent core shared by ``server.py`` (the dashboard) and
``cli.py`` (the terminal):

  * Spawn the four stdio MCP servers and connect to Lenses MCP, inside an
    ExitStack so everything is torn down cleanly.
  * List each server's tools once (the Lenses list is sorted, so the
    diagnosis sub-agent sees a stable tool set across restarts).
  * Build the four sub-agents and the supervisor, per run, from the skills,
    servers and models the run asked for.
"""

from __future__ import annotations

import time
from contextlib import ExitStack
from typing import Callable, Iterable, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from strands import Agent, AgentSkills

from agent.config import LLM_GATEWAY_URL, PAGERDUTY_MODE
from agent.mcp_clients import (
    make_confluence_client,
    make_github_client,
    make_lenses_client,
    make_pagerduty_client,
    make_slack_client,
)
from agent.mcp_registry import MCP_SERVER_NAMES
from agent.skills_registry import list_available_skills, resolve_skill_paths
from agent.sub_agents.diagnosis import build_diagnosis_agent
from agent.sub_agents.forensics import build_forensics_agent
from agent.sub_agents.reporter import build_reporter_agent
from agent.sub_agents.supervisor import build_supervisor
from agent.sub_agents.triage import build_triage_agent

console = Console()

# The Confluence tools that only read the knowledge base (see
# agent/mcp_servers/confluence.py). Everything else on that server publishes.
KB_READ_TOOLS = frozenset({"search_pages", "get_page"})


def _print_banner() -> None:
    banner = Panel.fit(
        "[bold cyan]Kafka SRE Agent[/bold cyan]\n"
        "[dim]Strands supervisor · 4 sub-agents · 5 MCP servers[/dim]",
        border_style="cyan",
        padding=(1, 4),
    )
    console.print(banner)


def _print_summary(response: object) -> None:
    panel = Panel(
        str(response),
        title="[bold green]Final SRE summary[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(panel)


# (enabled_skills, enabled_servers, model_overrides) -> supervisor; see
# ``make_supervisor`` below.
SupervisorFactory = Callable[..., Agent]


def build_supervisor_in_stack(
    stack: ExitStack, *, quiet: bool = False
) -> Tuple[SupervisorFactory, dict, dict]:
    """Spawn MCP clients into ``stack`` and return a supervisor factory.

    Used by both the CLI (per-run stack inside ``run()``) and the FastAPI
    server (process-lifetime stack inside its ASGI ``lifespan``). The caller
    owns ``stack`` and is responsible for keeping it open until the
    supervisor is no longer needed - MCP child processes get torn down when
    the stack closes.

    The returned ``make_supervisor`` callable builds a fresh supervisor on
    each call:

    * ``enabled_skills`` filters the diagnosis sub-agent's ``AgentSkills``
      plugin. ``None`` = every skill in :mod:`agent.skills_registry`;
      empty iterable = no ``skills`` tool at all.
    * ``enabled_servers`` filters which MCP server tool lists reach which
      sub-agent. ``None`` = every server in :mod:`agent.mcp_registry`;
      empty iterable = every sub-agent is built with no MCP tools.
    * ``model_overrides`` maps a role (supervisor, triage, diagnosis,
      forensics, reporter) to a gateway alias; missing roles use their
      config default.

    MCP clients themselves stay open in ``stack`` across calls (warm);
    only the four sub-agent ``Agent`` instances and the supervisor's
    ``@tool`` closures are rebuilt per call. That's cheap - pure
    in-process construction.

    Args:
        stack: An open ``ExitStack`` the MCP clients will be registered with.
        quiet: When True, suppress the spinner + tool-count banner (useful
            for the server's startup logs).

    Returns:
        ``(make_supervisor, info, clients)``: ``info`` carries the tool counts
        so the caller can log them, ``clients`` the open MCP clients by
        integration name.
    """
    # name -> client. Insertion order is the teardown order via ExitStack.
    clients = {
        "pagerduty": make_pagerduty_client(),
        "github": make_github_client(),
        "confluence": make_confluence_client(),
        "slack": make_slack_client(),
        "lenses": make_lenses_client(),
    }
    # Enter every MCP client as a context manager so child processes are
    # torn down cleanly on the way out (success or exception).
    for client in clients.values():
        stack.enter_context(client)

    def _list_tools() -> dict:
        tools = {name: c.list_tools_sync() for name, c in clients.items()}
        # MCP doesn't mandate a stable tool ordering - sort the Lenses tool
        # list by name so the diagnosis agent sees a deterministic tool set.
        tools["lenses"] = sorted(tools["lenses"], key=lambda t: t.tool_name)
        return tools

    if quiet:
        tools = _list_tools()
    else:
        with console.status("[bold cyan]Connecting to MCP servers...", spinner="dots"):
            tools = _list_tools()

    # Key pattern ``{name}_tools`` is what server.py's /mcp_servers reads.
    info = {f"{name}_tools": len(t) for name, t in tools.items()}

    if not quiet:
        console.print(
            f"[green]MCP ready[/green] - "
            f"PagerDuty: {info['pagerduty_tools']} tools, "
            f"Lenses: {info['lenses_tools']} tools, "
            f"GitHub: {info['github_tools']} tools, "
            f"Confluence: {info['confluence_tools']} tools, "
            f"Slack: {info['slack_tools']} tools"
        )

    available_skill_names = {s.name for s in list_available_skills()}

    def make_supervisor(
        enabled_skills: Optional[Iterable[str]] = None,
        enabled_servers: Optional[Iterable[str]] = None,
        model_overrides: Optional[dict[str, str]] = None,
    ) -> Agent:
        mo = model_overrides or {}
        # ---- skills -----------------------------------------------------
        if enabled_skills is None:
            skill_set = set(available_skill_names)
        else:
            skill_set = set(enabled_skills) & available_skill_names

        skills_plugin = None
        if skill_set:
            paths = resolve_skill_paths(skill_set)
            skills_plugin = AgentSkills(skills=[str(p) for p in paths])

        # ---- MCP servers ------------------------------------------------
        # None means "all servers"; an empty iterable means "no servers".
        # Either way, only validated names that match the registry count.
        if enabled_servers is None:
            server_set = set(MCP_SERVER_NAMES)
        else:
            server_set = set(enabled_servers) & MCP_SERVER_NAMES

        def _tools_for(name: str) -> list:
            return tools[name] if name in server_set else []

        has_pagerduty = "pagerduty" in server_set
        has_lenses = "lenses" in server_set
        has_github = "github" in server_set
        has_confluence = "confluence" in server_set
        has_slack = "slack" in server_set

        # The Confluence server is both the team knowledge base and the
        # publisher: triage gets only its read tools (runbook, service page,
        # past incidents), the reporter gets all of them.
        confluence_tools = _tools_for("confluence")
        kb_tools = [t for t in confluence_tools if t.tool_name in KB_READ_TOOLS]
        has_kb = bool(kb_tools)

        triage_tools = _tools_for("pagerduty") + kb_tools
        lenses_tools = _tools_for("lenses")
        github_tools = _tools_for("github")
        reporter_tools = confluence_tools + _tools_for("slack")
        # Live PagerDuty is the vendor's own MCP server with write access, so
        # the reporter shares triage's tools to leave the closing note on the
        # incident. The stub has nothing to write to.
        pagerduty_live = has_pagerduty and PAGERDUTY_MODE == "live"
        if pagerduty_live:
            reporter_tools = reporter_tools + _tools_for("pagerduty")

        # The sub-agents are rebuilt per call because their tool lists and
        # prompts depend on the toggles. The MCP clients are not touched:
        # this only reslices the cached tool lists captured above.
        triage = build_triage_agent(
            triage_tools,
            has_pagerduty=has_pagerduty,
            pagerduty_live=pagerduty_live,
            has_kb=has_kb,
            model=mo.get("triage"),
        )
        forensics = build_forensics_agent(
            github_tools,
            has_github=has_github,
            model=mo.get("forensics"),
        )
        reporter = build_reporter_agent(
            reporter_tools,
            has_confluence=has_confluence,
            has_kb=has_kb,
            has_slack=has_slack,
            pagerduty_notes=pagerduty_live,
            skills_plugin=skills_plugin,
            enabled_skill_names=sorted(skill_set),
            model=mo.get("reporter"),
        )
        diagnosis = build_diagnosis_agent(
            lenses_tools,
            skills_plugin=skills_plugin,
            has_lenses=has_lenses,
            enabled_skill_names=sorted(skill_set),
            model=mo.get("diagnosis"),
        )
        return build_supervisor(
            triage=triage,
            diagnosis=diagnosis,
            forensics=forensics,
            reporter=reporter,
            model=mo.get("supervisor"),
            has_pagerduty=has_pagerduty,
        )

    return make_supervisor, info, clients


def run(incident_payload: str) -> None:
    """Run one full incident-response cycle and print the summary.

    ``incident_payload`` is the incident's raw JSON; the CLI reads it from a
    file, stdin, or the ``--demo`` flag.
    """
    if not incident_payload:
        raise ValueError(
            "incident_payload is required. Pass --demo, a file path, or "
            "pipe JSON via stdin to the CLI."
        )

    _print_banner()
    console.print(f"[dim]LLM gateway: {LLM_GATEWAY_URL}[/dim]")

    with ExitStack() as stack:
        make_supervisor, _info, _clients = build_supervisor_in_stack(stack)
        supervisor = make_supervisor()  # every skill and server

        prompt = (
            "A new PagerDuty incident has fired. Run the full incident-response "
            "workflow end-to-end. Here is the incident payload:\n\n"
            f"{incident_payload}"
        )

        console.print("\n[bold]Supervisor invoked.[/bold]\n")
        start = time.perf_counter()

        response = supervisor(prompt)

        elapsed = time.perf_counter() - start

        console.print(f"\n[dim]Workflow complete in {elapsed:.1f}s.[/dim]\n")
        _print_summary(response)
