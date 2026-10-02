#!/usr/bin/env python3
"""Register model pricing in Phoenix so traces show cost instead of $0.

Phoenix computes a span's cost itself, from token counts times a pricing
entry matched on ``llm.model_name``, and shows that entry's name as the
span's model. The agent's spans carry the provider model behind each gateway
alias (``claude-sonnet-5-5``, ``gpt-4o``; see agent/tracing.py). Phoenix's
built-in entries price most of them; these cover the rest: ids it has no
entry for (Mistral's, ``claude-haiku-5-5``), and ``claude-sonnet-5-5``, which
its ``claude-sonnet-5`` pattern would otherwise claim at Sonnet 5's prices. Without them, a span
prices at $0.00 with no error anywhere.

The entries are registered without a provider, so they match on name alone.

Pricing is applied at ingestion: spans recorded before an entry existed keep
cost = 0. The entries live in the ``phoenix-data`` volume, which is why this
runs on every ``make up``. Idempotent: the script replaces its own entries.

Usage:
    python harness/seed/seed_phoenix_costs.py [--endpoint http://localhost:6006]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# USD per million tokens. The dashboard prices runs with the same figures
# (ui/src/lib/models.ts): change both together. Check the providers' pricing
# pages before quoting a cost: a stale entry produces confidently wrong numbers.
#   https://platform.claude.com/docs/en/about-claude/pricing
#   https://mistral.ai/pricing/api
# Named after the model id, like Phoenix's built-in entries. claude-haiku-4-5
# and gpt-4o are built in, at the same prices as the dashboard's.
MODELS = [
    {
        "name": "claude-sonnet-5-5",  # gateway alias: claude
        "namePattern": r"^claude-sonnet-5-5$",
        "costs": {"input": 2.0, "cache_read": 0.1, "cache_write": 2.5, "output": 10.0},
    },
    {
        # Up to 100K prompt tokens. Over that a call pays five times as much,
        # which a flat entry can't express: such a call shows a fifth of its cost.
        "name": "claude-haiku-5-5",  # gateway alias: claude-haiku-5-5
        "namePattern": r"^claude-haiku-5-5$",
        "costs": {"input": 0.1, "cache_read": 0.01, "cache_write": 0.125, "output": 0.5},
    },
    {
        "name": "mistral-medium-2604",  # gateway alias: mistral-medium
        "namePattern": r"^mistral-medium-2604$",
        "costs": {"input": 1.5, "output": 7.5},
    },
    {
        "name": "mistral-large-latest",  # gateway alias: mistral-large
        "namePattern": r"^mistral-large-latest$",
        "costs": {"input": 2.0, "output": 6.0},
    },
]
# Gateway models Phoenix prices out of the box (tests/test_tracing.py checks
# every model in agent/gateway/litellm.yaml is here or in MODELS).
BUILT_IN = {"claude-haiku-4-5", "gpt-4o"}
# Entries earlier versions of this script registered, keyed on the aliases.
LEGACY_PREFIX = "gateway alias "


def owned(name: str) -> bool:
    return name.startswith(LEGACY_PREFIX) or name in {m["name"] for m in MODELS}

CREATE = """mutation($input: CreateModelMutationInput!){
  createModel(input:$input){ model { id name provider namePattern } }
}"""
DELETE = """mutation($input: DeleteModelMutationInput!){
  deleteModel(input:$input){ model { name } }
}"""
LIST = """{ generativeModels(first:500){ edges { node { id name kind } } } }"""


def gql(endpoint: str, query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/graphql",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"])[:400])
    return payload["data"]


def main() -> int:
    default_endpoint = os.environ.get(
        "PHOENIX_ENDPOINT",
        f"http://localhost:{os.environ.get('HOST_PORT_PHOENIX') or '6006'}",
    )
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=default_endpoint)
    args = ap.parse_args()

    # `make up` runs this right after starting Phoenix, so give it a minute.
    for attempt in range(30):
        try:
            ours = [
                e["node"]["id"]
                for e in gql(args.endpoint, LIST)["generativeModels"]["edges"]
                if e["node"]["kind"] == "CUSTOM" and owned(e["node"]["name"])
            ]
            break
        except (urllib.error.URLError, OSError) as exc:
            if attempt == 29:
                print(f"[phoenix-costs] Phoenix unreachable at {args.endpoint} ({exc}); skipping.")
                return 0  # non-fatal: the stack is useful without cost
            time.sleep(2)

    for model_id in ours:
        gql(args.endpoint, DELETE, {"input": {"id": model_id}})
    for m in MODELS:
        gql(
            args.endpoint,
            CREATE,
            {
                "input": {
                    "name": m["name"],
                    "namePattern": m["namePattern"],  # no provider: see docstring
                    "costs": [
                        {
                            "tokenType": token_type,
                            "kind": "COMPLETION" if token_type == "output" else "PROMPT",
                            "costPerMillionTokens": price,
                        }
                        for token_type, price in m["costs"].items()
                    ],
                }
            },
        )
        prices = ", ".join(f"{k} ${v}/M" for k, v in m["costs"].items())
        print(f"[phoenix-costs] {m['name']}: {prices} (pattern {m['namePattern']})")
    print("[phoenix-costs] done - applies to NEW traces only, not existing ones.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
