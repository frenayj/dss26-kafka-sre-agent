"""Every repo in the DSS26 Bank GitHub org, loaded from ``repos/``.

Each module under ``repos/`` exposes either ``REPO_SPEC`` (one repo) or
``REPO_SPECS`` (several, e.g. the generated backdrop repos).
"""

from __future__ import annotations

import sys
from importlib import import_module

from model import RepoSpec

REPO_MODULES: tuple[str, ...] = (
    # Tier A - the incidents happen here.
    "merchant_gateway",
    "fraud_decisioning_svc",
    "kafka_platform",
    "cards_ci_workflows",
    # Tier B/C - neighbours and backdrop, plus the org profile.
    "backdrop",
    "org_profile",
)


def load_repos(only: tuple[str, ...] | None = None, strict: bool = True) -> list[RepoSpec]:
    specs: list[RepoSpec] = []
    for mod_name in REPO_MODULES:
        try:
            mod = import_module(f"repos.{mod_name}")
        except ModuleNotFoundError as exc:
            if strict or exc.name != f"repos.{mod_name}":
                raise
            print(f"[catalog] skipping repos/{mod_name}.py (not written yet)", file=sys.stderr)
            continue
        found = getattr(mod, "REPO_SPECS", None) or (mod.REPO_SPEC,)
        specs.extend(found)

    names = [s.name for s in specs]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"duplicate repo names: {sorted(dupes)}")
    keys = [pr.key for s in specs for pr in s.prs]
    dupe_keys = {k for k in keys if keys.count(k) > 1}
    if dupe_keys:
        raise ValueError(f"duplicate scenario PR keys: {sorted(dupe_keys)}")

    if only:
        unknown = set(only) - set(names)
        if unknown:
            raise KeyError(f"unknown repo(s): {sorted(unknown)}")
        specs = [s for s in specs if s.name in only]
    return specs
