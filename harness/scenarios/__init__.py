"""The demo's incident scenarios, one folder each.

    harness/scenarios/<name>/
        scenario.json   title, summary, page_delay_s
        incident.json   the alert, as PagerDuty returns an incident a
                        Datadog monitor raised
        induce.sh       break the cluster (and merge the culprit PR)
        reset.sh        restore it; idempotent

Everything that runs a scenario finds it here: the Makefile targets, the
operator console, the PagerDuty stub and the paging script. Adding a scenario
is adding a folder (see README.md).

    python3 -m harness.scenarios list
    python3 -m harness.scenarios incident <name>   # the alert, stamped "now"

Standard library only, like the rest of the host-side harness.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

SCENARIOS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Scenario:
    name: str  # the folder name, e.g. "consumer-lag"
    title: str
    summary: str
    page_delay_s: int  # how long after induce.sh the alert is worth paging
    path: Path

    @property
    def induce(self) -> Path:
        return self.path / "induce.sh"

    @property
    def reset(self) -> Path:
        return self.path / "reset.sh"

    def incident(self) -> Dict[str, Any]:
        """The alert with its wall-clock fields set to now (see :func:`freshen`)."""
        return freshen(json.loads((self.path / "incident.json").read_text()))


def names() -> List[str]:
    """Every scenario folder, sorted."""
    return sorted(p.parent.name for p in SCENARIOS_DIR.glob("*/scenario.json"))


def load(name: str) -> Scenario:
    path = SCENARIOS_DIR / name
    try:
        meta = json.loads((path / "scenario.json").read_text())
    except FileNotFoundError:
        raise KeyError(f"no scenario {name!r} (have: {', '.join(names())})") from None
    return Scenario(
        name=name,
        title=meta["title"],
        summary=meta.get("summary", ""),
        page_delay_s=int(meta.get("page_delay_s", 45)),
        path=path,
    )


def all_scenarios() -> List[Scenario]:
    return [load(n) for n in names()]


def freshen(incident: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-copy an incident and set ``created_at`` / ``updated_at`` /
    ``assignments[].at`` to now.

    Everything else (ids, URLs, numbers, prose) stays stable, so the alert
    always looks freshly fired without its identifiers drifting between runs.
    The forensics agent searches the PRs merged in the 24 hours before
    ``created_at``, so a stale date would send it to the wrong day.
    """
    payload = copy.deepcopy(incident)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inc = payload["incident"]
    inc["created_at"] = now
    inc["updated_at"] = now
    for assignment in inc.get("assignments") or []:
        if isinstance(assignment, dict):
            assignment["at"] = now
    return payload
