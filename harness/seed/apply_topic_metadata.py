"""Apply rich descriptions + tags to the demo's Kafka topics in Lenses HQ.

The Lenses agent's auto-discovery surfaces the topics but doesn't carry any
documentation. This script PUTs descriptions and tag sets via the HQ proxy
API so the topics look the way a real global-FSI cards platform's catalogue
would look - and so the diagnosis sub-agent has prose context when it
inspects a dataset.

The list of topics + their metadata lives in ``harness/seed/demo_topics.py`` -
two live topics (auto-created by their producers) plus 30 catalogue-only
fakes seeded by ``harness/seed/seed_demo_topics.py``. This script just loops.

Idempotent: re-running just overwrites with the same content. Safe to call
after every ``make up`` (or any time topics get recreated by ``reset.sh``).

Logs into HQ with ``DEMO_HQ_USER`` / ``DEMO_HQ_PASSWORD`` (or the defaults
from docker-compose: admin / admin). Reads the HQ URL from
``LENSES_HQ_URL`` or defaults to http://localhost:9991 (``HOST_PORT_HQ``).

The environment and then each topic are polled for up to
``DATASET_WAIT_SECONDS`` (default 120s) before applying - covers the gap
between the Lenses agent registering, topic creation / producer first-write,
and HQ's auto-discovery loop noticing the new dataset.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Iterable

import requests
from demo_topics import TOPICS

HQ_URL = (
    os.environ.get("LENSES_HQ_URL") or f"http://localhost:{os.environ.get('HOST_PORT_HQ') or '9991'}"
).rstrip("/")
HQ_USER = os.environ.get("DEMO_HQ_USER", "admin")
HQ_PASSWORD = os.environ.get("DEMO_HQ_PASSWORD", "admin")
WAIT_SECONDS = int(os.environ.get("DATASET_WAIT_SECONDS", "120"))

# The HQ environment the Lenses agent registers (DEMO_HQ_ENV_NAME in
# harness/stack/docker-compose.yml).
ENV = "cards-prod-euw1"
ENV_URL = f"{HQ_URL}/api/v1/environments/{ENV}"


def login(session: requests.Session) -> None:
    resp = session.post(
        f"{HQ_URL}/api/v1/login",
        json={"username": HQ_USER, "password": HQ_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()


def wait_for(session: requests.Session, url: str) -> bool:
    """Poll ``url`` until it returns 200, up to WAIT_SECONDS."""
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        try:
            if session.get(url, timeout=5).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def dataset_url(topic: str) -> str:
    return f"{ENV_URL}/proxy/api/v1/datasets/kafka/{topic}"


def apply_one(
    session: requests.Session, topic: str, description: str, tags: Iterable[str]
) -> bool:
    print(f"[metadata] {topic}: waiting for dataset to appear...")
    if not wait_for(session, dataset_url(topic)):
        print(
            f"[metadata]   SKIP - dataset not present after {WAIT_SECONDS}s "
            f"(produce something to it first?)"
        )
        return False
    r = session.put(
        f"{dataset_url(topic)}/description", json={"description": description}, timeout=10
    )
    r.raise_for_status()
    tag_list = list(tags)
    payload: dict[str, Any] = {"tags": [{"name": t} for t in tag_list]}
    r = session.put(f"{dataset_url(topic)}/tags", json=payload, timeout=10)
    r.raise_for_status()
    print(f"[metadata]   ok - description + {len(tag_list)} tag(s) applied")
    return True


def main() -> int:
    print(f"[metadata] HQ: {HQ_URL}  user: {HQ_USER}  environment: {ENV}")
    print(f"[metadata] {len(TOPICS)} topics in catalogue")
    s = requests.Session()
    try:
        login(s)
    except requests.RequestException as exc:
        print(f"[metadata] ERROR: login failed: {exc}", file=sys.stderr)
        return 1

    # Fail fast if the environment never registers, rather than waiting out
    # every dataset in turn.
    if not wait_for(s, ENV_URL):
        print(
            f"[metadata] ERROR: environment {ENV} not in HQ after {WAIT_SECONDS}s "
            "- is the Lenses agent running?",
            file=sys.stderr,
        )
        return 1

    applied = 0
    skipped = 0
    for spec in TOPICS:
        try:
            ok = apply_one(s, spec.name, spec.description, spec.tags)
            if ok:
                applied += 1
            else:
                skipped += 1
        except requests.HTTPError as exc:
            print(
                f"[metadata]   ERROR on {spec.name}: HTTP "
                f"{exc.response.status_code} {exc.response.text[:200]}",
                file=sys.stderr,
            )
            skipped += 1

    print(f"[metadata] done - {applied} applied, {skipped} skipped")
    return 0 if applied > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
