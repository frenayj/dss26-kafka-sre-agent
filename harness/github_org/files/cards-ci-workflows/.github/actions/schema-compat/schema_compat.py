#!/usr/bin/env python3
"""Fail if a pull request makes an Avro schema incompatible with its base version.

For every ``<subject>=<path>`` pair:

1. read the schema at ``<path>`` in the working tree - the pull request's version;
2. read the same path at the base revision with ``git show``. A schema that
   does not exist there is new and has nothing to be compatible with;
3. register the base version under ``<subject>`` in a throwaway Schema
   Registry, then ask the registry whether the new version can follow it:
   ``POST /compatibility/subjects/<subject>/versions/latest?verbose=true``.

The registry is set to BACKWARD first - the level every cards subject uses -
so the answer is the one production would give when the producer registers
the new version.

Inputs come from the environment (set by action.yml) or the command line:
SCHEMAS, BASE_REF and SCHEMA_REGISTRY_URL. Writes an error annotation on each
failing schema file and a table to $GITHUB_STEP_SUMMARY.

    python3 schema_compat.py --base-ref origin/main \\
        --schemas 'cards.clearing.matched.v1-value=src/main/avro/clearing-matched.avsc'
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

LEVEL = "BACKWARD"
CONTENT_TYPE = "application/vnd.schemaregistry.v1+json"


class RegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class Pair:
    subject: str
    path: str


@dataclass(frozen=True)
class Result:
    pair: Pair
    status: str  # compatible | incompatible | new | unchanged | error
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.status in ("incompatible", "error")


def parse_pairs(text: str) -> list[Pair]:
    """One ``<subject>=<path>`` per line; blank lines and ``#`` comments ignored."""
    pairs: list[Pair] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        subject, sep, path = line.partition("=")
        if not sep or not subject.strip() or not path.strip():
            raise ValueError(f"line {number}: expected <subject>=<path>, got {raw.strip()!r}")
        pairs.append(Pair(subject.strip(), path.strip()))
    if not pairs:
        raise ValueError("no <subject>=<path> pairs in the schemas input")
    return pairs


class Registry:
    def __init__(self, url: str, timeout: float = 10.0):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.url + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": CONTENT_TYPE, "Accept": CONTENT_TYPE},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace").strip()
            raise RegistryError(f"{method} {path}: HTTP {exc.code} {detail}") from None

    def wait_until_ready(self, attempts: int = 30, delay: float = 2.0) -> None:
        """The container can pass its health check before the registry serves requests."""
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self.call("GET", "/subjects")
                return
            except (RegistryError, OSError) as exc:
                last = exc
                print(f"waiting for Schema Registry ({attempt}/{attempts}): {exc}", flush=True)
                time.sleep(delay)
        raise RegistryError(f"Schema Registry at {self.url} is not answering: {last}")

    def set_level(self, level: str) -> None:
        self.call("PUT", "/config", {"compatibility": level})

    def register(self, subject: str, schema: str) -> int:
        doc = self.call("POST", f"/subjects/{_quote(subject)}/versions", {"schema": schema})
        return int(doc["id"])

    def check(self, subject: str, schema: str) -> tuple[bool, list[str]]:
        doc = self.call(
            "POST",
            f"/compatibility/subjects/{_quote(subject)}/versions/latest?verbose=true",
            {"schema": schema},
        )
        return bool(doc.get("is_compatible")), [str(m) for m in doc.get("messages") or ()]


def _quote(subject: str) -> str:
    return urllib.parse.quote(subject, safe="")


def base_version(ref: str, path: str, cwd: Path) -> str | None:
    """The file at ``ref``, or None if it does not exist there."""
    proc = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=cwd,
                          capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def check_pair(registry: Registry, pair: Pair, base_ref: str, root: Path) -> Result:
    file = root / pair.path
    if not file.is_file():
        return Result(pair, "error", f"{pair.path} does not exist")
    head = file.read_text()
    try:
        head_doc = json.loads(head)
    except json.JSONDecodeError as exc:
        return Result(pair, "error", f"{pair.path} is not valid JSON: {exc}")

    base = base_version(base_ref, pair.path, root)
    if base is None:
        return Result(pair, "new", f"not on {base_ref[:12]}, nothing to compare")
    try:
        if json.loads(base) == head_doc:
            return Result(pair, "unchanged")
    except json.JSONDecodeError:
        pass  # a broken base version is still worth comparing against

    try:
        registry.register(pair.subject, base)
        ok, messages = registry.check(pair.subject, head)
    except RegistryError as exc:
        return Result(pair, "error", str(exc))
    # The registry echoes the whole old schema as one of the messages; the
    # annotation only needs the reasons.
    reasons = [m for m in messages if not m.startswith("{oldSchema:")]
    return Result(pair, "compatible" if ok else "incompatible", "; ".join(reasons))


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def annotate(result: Result) -> str | None:
    if not result.failed:
        return None
    if result.status == "incompatible":
        title = f"{result.pair.subject} is not {LEVEL} compatible"
    else:
        title = f"schema-compat could not check {result.pair.subject}"
    detail = result.detail or "the registry gave no reason"
    return (f"::error file={_escape_property(result.pair.path)},"
            f"title={_escape_property(title)}::{_escape_data(detail)}")


def summary(results: list[Result], base_ref: str) -> str:
    lines = [f"### Avro schema compatibility ({LEVEL}, base `{base_ref[:12]}`)", "",
             "| Subject | Schema | Result |", "|---|---|---|"]
    for r in results:
        note = f" - {r.detail}" if r.detail else ""
        lines.append(f"| `{r.pair.subject}` | `{r.pair.path}` | {r.status}{note} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--schemas", default=os.environ.get("SCHEMAS", ""))
    ap.add_argument("--base-ref", default=os.environ.get("BASE_REF", ""))
    ap.add_argument("--registry-url",
                    default=os.environ.get("SCHEMA_REGISTRY_URL", "http://localhost:8081"))
    ap.add_argument("--root", type=Path, default=Path.cwd())
    args = ap.parse_args(argv)

    try:
        pairs = parse_pairs(args.schemas)
    except ValueError as exc:
        print(f"::error title=schema-compat::{_escape_data(str(exc))}")
        return 2
    # Pushes that create a branch carry an all-zero "before" SHA.
    if not args.base_ref.strip("0"):
        print("::notice title=schema-compat::no base revision to compare against - skipped")
        return 0

    registry = Registry(args.registry_url)
    registry.wait_until_ready()
    registry.set_level(LEVEL)
    results = [check_pair(registry, pair, args.base_ref, args.root) for pair in pairs]

    for result in results:
        line = annotate(result)
        print(line or f"{result.pair.subject}: {result.status}")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as fh:
            fh.write(summary(results, args.base_ref))

    failed = [r for r in results if r.failed]
    print(f"{len(results)} schema(s) checked at {LEVEL}: {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
