"""Run the agent on one incident from the terminal.

    python -m agent.cli incident.json           # from a file
    cat incident.json | python -m agent.cli     # via stdin

The incident is PagerDuty-shaped JSON. To run a demo scenario's alert
(``make run`` does this):

    python3 -m harness.scenarios incident consumer-lag | python -m agent.cli
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console

console = Console()


_USAGE = (
    "Usage:\n"
    "  python -m agent.cli incident.json     # read incident from a file\n"
    "  cat incident.json | python -m agent.cli   # read from stdin\n"
)


def _load_incident(args: list[str]) -> str:
    """Return the incident payload as a JSON string; exit on a usage error."""
    if any(a in {"-h", "--help"} for a in args):
        console.print(_USAGE)
        sys.exit(0)

    # File path?
    if args:
        path = Path(args[0])
        if not path.exists():
            console.print(f"[red]Incident file not found: {path}[/red]")
            sys.exit(1)
        raw = path.read_text()
    elif not sys.stdin.isatty():
        # Piped stdin.
        raw = sys.stdin.read()
    else:
        console.print(_USAGE)
        console.print(
            "[yellow]No incident provided. Pass a path or pipe JSON.[/yellow]"
        )
        sys.exit(2)

    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Incident payload is not valid JSON: {exc}[/red]")
        sys.exit(1)
    return raw


def main() -> None:
    incident_payload = _load_incident(sys.argv[1:])
    # Imported late so ``--help`` returns without loading strands / mcp.
    from agent.runner import run

    run(incident_payload)


if __name__ == "__main__":
    main()
