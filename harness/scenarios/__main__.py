"""``python3 -m harness.scenarios list | incident <name> | get <name> <field>``."""

from __future__ import annotations

import argparse
import json
import sys

from harness.scenarios import all_scenarios, load


def main() -> None:
    parser = argparse.ArgumentParser(prog="python3 -m harness.scenarios")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="one line per scenario")
    inc = sub.add_parser("incident", help="print a scenario's alert, stamped now")
    inc.add_argument("name")
    get = sub.add_parser("get", help="print one field of a scenario (for the Makefile)")
    get.add_argument("name")
    get.add_argument("field", choices=["title", "summary", "page_delay_s"])
    args = parser.parse_args()

    try:
        if args.cmd == "list":
            for s in all_scenarios():
                print(f"{s.name:16s} {s.title}")
        elif args.cmd == "incident":
            print(json.dumps(load(args.name).incident(), indent=2))
        else:
            print(getattr(load(args.name), args.field))
    except KeyError as exc:
        sys.exit(str(exc.args[0]))


if __name__ == "__main__":
    main()
