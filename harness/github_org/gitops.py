#!/usr/bin/env python3
"""Apply what is on ``main`` in the dss26-org repos to the demo cluster.

This stands in for the bank's deploy pipeline, which in the story runs on
merge:

* ``gitops.py schema [--env prod]`` - merchant-gateway's release pipeline:
  ``schema-registry:set-compatibility`` then ``schema-registry:register`` with
  the subject, compatibility level and .avsc declared in its pom.xml.

Reading the change from GitHub (rather than from a local copy) is the point:
the cluster ends up in exactly the state the merged commit describes, so the
diff the agent finds on GitHub and the config it sees in Lenses agree because
one produced the other.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gh import GitHub  # noqa: E402
from model import ORG  # noqa: E402

GATEWAY_REPO = "merchant-gateway"
AUTH_SUBJECT = "cards.authorisation.requested.v1-value"
SR_HEADER = {"Content-Type": "application/vnd.schemaregistry.v1+json"}


def log(msg: str) -> None:
    print(f"[gitops] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def pom_schema_settings(pom: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return (subject -> avsc path, subject -> compatibility) from the plugin config."""

    def block(tag: str) -> dict[str, str]:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", pom, re.S)
        if not m:
            return {}
        return {k: v.strip() for k, v in re.findall(r"<([^>/\s]+)>([^<]*)</\1>", m.group(1))}

    return block("subjects"), block("compatibilityLevels")


# ---------------------------------------------------------------------------
# Schema Registry
# ---------------------------------------------------------------------------


def _sr(method: str, url: str, payload: dict | None = None) -> tuple[int, str]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=SR_HEADER)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def apply_schema(gh: GitHub, env: str) -> int:
    if env != "prod":
        log("only prod is wired to the demo Schema Registry")
        return 2
    sr = (
        os.environ.get("SCHEMA_REGISTRY_PROD") or f"http://localhost:{os.environ.get('HOST_PORT_SR_PROD') or '8081'}"
    ).rstrip("/")
    pom = gh.read_file(ORG, GATEWAY_REPO, "pom.xml")
    if pom is None:
        log(f"{ORG}/{GATEWAY_REPO}: pom.xml not found on main")
        return 1
    subjects, levels = pom_schema_settings(pom)
    if AUTH_SUBJECT not in subjects:
        log(f"pom.xml declares no subject {AUTH_SUBJECT}")
        return 1
    schema = gh.read_file(ORG, GATEWAY_REPO, subjects[AUTH_SUBJECT])
    if schema is None:
        log(f"{subjects[AUTH_SUBJECT]} not found on main")
        return 1
    level = levels.get(AUTH_SUBJECT)

    log(f"release pipeline for {ORG}/{GATEWAY_REPO}@main -> {sr}")
    if level:
        status, body = _sr("PUT", f"{sr}/config/{AUTH_SUBJECT}", {"compatibility": level})
        log(f"set-compatibility {AUTH_SUBJECT}={level}: HTTP {status} {body.strip()}")
        if status >= 300:
            return 1
    status, body = _sr("POST", f"{sr}/subjects/{AUTH_SUBJECT}/versions", {"schema": schema})
    log(f"register {subjects[AUTH_SUBJECT]}: HTTP {status} {body.strip()}")
    return 0 if status < 300 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("schema")
    p.add_argument("--env", default="prod")
    args = ap.parse_args(argv)
    return apply_schema(GitHub(), args.env)


if __name__ == "__main__":
    sys.exit(main())
