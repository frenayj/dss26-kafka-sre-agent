#!/usr/bin/env python3
"""Seed the DSS26 Bank GitHub org (``dss26-org``) from the declarations in repos/.

Offline commands (no GitHub access):

    seed.py validate [repo ...]        replay history + walk every scenario PR
    seed.py build <repo> --out DIR      write the seeded repo to DIR/<repo>
          [--apply decoys,culprit,open]  ...optionally with scenario PRs applied

GitHub commands (need a token with repo + admin:org, and delete_repo for
--rebuild; defaults to ``gh auth token``):

    seed.py teams                       create/update teams and their nesting
    seed.py push [repo ...]             create missing repos and push their history
          [--rebuild]                    delete and recreate the repos first
    seed.py status                      what exists, and each scenario PR's state

``push`` is idempotent: an existing non-empty repo keeps its history (only
settings, topics, labels and team grants are re-applied). ``--rebuild`` is the
only way to rewrite history, and it deletes every PR with the repo - that is
the point: it returns the org to a clean pre-demo state.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog import load_repos  # noqa: E402
from model import ReplayError, apply_ops  # noqa: E402
from replay import build, validate  # noqa: E402


def cmd_validate(args) -> int:
    failed = 0
    specs = load_repos(only=tuple(args.repos) or None, strict=not args.allow_missing)
    with tempfile.TemporaryDirectory(prefix="dss26-validate-") as tmp:
        for spec in specs:
            try:
                for line in validate(spec, Path(tmp)):
                    print(f"{spec.name:32} {line}")
            except (ReplayError, KeyError, ValueError) as exc:
                failed += 1
                print(f"{spec.name:32} FAILED: {exc}")
    print(f"\n{len(specs) - failed}/{len(specs)} repo(s) valid")
    return 1 if failed else 0


def cmd_build(args) -> int:
    (spec,) = load_repos(only=(args.repo,), strict=False)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    root = build(spec, out)
    wanted = {w.strip() for w in (args.apply or "").split(",") if w.strip()}
    for kind in ("open", "decoy", "culprit"):
        if kind + "s" in wanted or kind in wanted:
            for pr in (p for p in spec.prs if p.kind == kind):
                apply_ops(root, pr.ops, f"{spec.name}/{pr.key}")
                print(f"applied {kind} {pr.key} (working tree only, not committed)")
    print(root)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate")
    p.add_argument("repos", nargs="*")
    p.add_argument("--allow-missing", action="store_true",
                   help="skip repo modules that are not written yet")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("build")
    p.add_argument("repo")
    p.add_argument("--out", required=True)
    p.add_argument("--apply", help="comma list of: open,decoys,culprit")
    p.set_defaults(fn=cmd_build)

    try:
        import seed_github  # noqa: F401 - GitHub commands live next door
    except ImportError:
        seed_github = None
    if seed_github is not None:
        seed_github.register(sub)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
