"""Provision a Lenses HQ service account for the SRE agent, and print its token.

Why this exists
---------------
The agent reaches Lenses MCP with a credential. The default is interactive
OAuth: a human opens a browser, signs into HQ, and a token lands in the
agent's volume. That is fine to demo once and miserable for everything else -
it cannot be scripted, it expires after ~1h mid-run, and every person who
clones this repo has to do it before anything works.

This script mints the non-interactive alternative: a service-account token
that HQ recognises and that carries real permissions.

The part that is not obvious
----------------------------
HQ's REST API has TWO ways to express service-account group membership, and
only one of them works:

  * ``PATCH /service-accounts/{name}`` with ``{"groups": [...]}`` returns 200
    and silently discards the change. So does the group side, with names or
    ids, at create time or after. There is no error - the account simply ends
    up in no groups.
  * ``PUT /service-accounts/{name}/groups`` with ``{"set_groups": [...]}``
    actually works.

A service account in no groups holds no roles, and HQ then filters every
response down to nothing: the token authenticates, `/environments` returns
`{"items": []}`, and the MCP server reports zero tools with no error at all.
That failure is silent end to end, which is why it is worth a comment this
long. ``is_admin`` is likewise accepted and ignored - it is not a shortcut.

Usage
-----
    python3 harness/seed/provision_service_account.py            # print the token
    python3 harness/seed/provision_service_account.py --write    # + write it for compose

Re-running is safe: every step is idempotent, and an existing account has its
token renewed (HQ only returns a token at creation, so there is no way to
recover the old one).
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

HQ_URL = (
    os.environ.get("LENSES_HQ_URL") or f"http://localhost:{os.environ.get('HOST_PORT_HQ') or '9991'}"
).rstrip("/")
HQ_USER = os.environ.get("DEMO_HQ_USER", "admin")
HQ_PASSWORD = os.environ.get("DEMO_HQ_PASSWORD", "admin")

SA_NAME = os.environ.get("LENSES_SA_NAME", "sre-agent")
GROUP_NAME = f"{SA_NAME}-group"
ROLE_NAME = f"{SA_NAME}-role"

# The services HQ knows about are a closed set - an unknown one is rejected
# with "not a known service". These five are what the agent's tools touch:
# Kafka (topics, groups, SQL, Connect), the schema registry (the consumer-lag
# scenario lives there), the environment list (every MCP tool takes an
# `environment` argument, and without this the agent cannot even see one),
# plus alerts and governance for the wider catalogue views.
#
# Deliberately NOT `*`: this is a demo people copy, and "grant everything"
# is the wrong thing to copy. `iam:*` in particular is withheld - the agent
# has no business editing accounts or permissions.
POLICY_ACTIONS = [
    "kafka:*",
    "schemas:*",
    "environments:*",
    "alerts:*",
    "governance:*",
]

# Compose reads this with `env_file:`, so it must exist before `lenses-mcp`
# is created. Not named *.env on purpose - it holds a live, gitignored
# credential and should not be mistaken for the env file you edit by hand.
CRED_FILE = REPO_ROOT / "harness" / "stack" / "sa-credentials.conf"


def _die(msg: str) -> None:
    sys.exit(f"[provision] ERROR: {msg}")


class Response:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content
        self.text = content.decode(errors="replace")

    def json(self) -> dict:
        return json.loads(self.content)


class Session:
    """The few calls this script needs, on the stdlib, so `make up` runs on
    any host python3. HQ authenticates with a session cookie, kept in the jar."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def request(self, method, url, json_body=None, headers=None, timeout=15) -> Response:
        data = None if json_body is None else json.dumps(json_body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return Response(resp.status, resp.read())
        except urllib.error.HTTPError as exc:
            return Response(exc.code, exc.read())

    def get(self, url, **kw) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url, json=None, **kw) -> Response:
        return self.request("POST", url, json_body=json, **kw)

    def patch(self, url, json=None, **kw) -> Response:
        return self.request("PATCH", url, json_body=json, **kw)

    def put(self, url, json=None, **kw) -> Response:
        return self.request("PUT", url, json_body=json, **kw)


def login(wait_seconds: int = 180) -> Session:
    """Log into HQ, waiting for it to come up.

    `make up` calls this immediately after starting HQ, so "connection
    refused" is the normal first answer rather than an error - poll until it
    answers or the budget runs out.
    """
    s = Session()
    deadline = time.time() + wait_seconds
    last = ""
    while True:
        try:
            r = s.post(
                f"{HQ_URL}/api/v1/login",
                json={"username": HQ_USER, "password": HQ_PASSWORD},
                timeout=10,
            )
            if r.status_code == 200:
                # HQ authenticates with a session cookie, not a bearer token -
                # the login body is `{}`. The cookie lives on the session.
                return s
            if r.status_code in (401, 403):
                _die(f"HQ rejected {HQ_USER}. Check DEMO_HQ_USER/DEMO_HQ_PASSWORD.")
            last = f"HTTP {r.status_code}"
        except (urllib.error.URLError, OSError) as exc:
            last = type(exc).__name__
        if time.time() >= deadline:
            _die(f"Lenses HQ at {HQ_URL} not ready after {wait_seconds}s ({last})")
        print(f"[provision] waiting for HQ at {HQ_URL} ({last})...")
        time.sleep(5)


def _ok(r: Response, what: str) -> dict:
    if r.status_code >= 400:
        _die(f"{what} failed ({r.status_code}): {r.text[:300]}")
    return r.json() if r.content else {}


def ensure_role(s: Session) -> None:
    existing = _ok(s.get(f"{HQ_URL}/api/v1/roles", timeout=15), "list roles")
    names = {r["name"] for r in existing.get("items", [])}
    if ROLE_NAME not in names:
        _ok(
            s.post(f"{HQ_URL}/api/v1/roles", json={"name": ROLE_NAME}, timeout=15),
            "create role",
        )
        print(f"[provision] created role {ROLE_NAME}")
    # PATCH is safe to repeat and is how the policy gets set either way -
    # role creation does not accept a policy inline.
    role = _ok(
        s.patch(
            f"{HQ_URL}/api/v1/roles/{ROLE_NAME}",
            json={"policy": [{"effect": "allow", "action": POLICY_ACTIONS, "resource": ["*"]}]},
            timeout=15,
        ),
        "set role policy",
    )
    print(f"[provision] role {ROLE_NAME} policy: {', '.join(POLICY_ACTIONS)}")
    if not role.get("policy"):
        _die("role policy came back empty - HQ rejected the actions")


def ensure_group(s: Session) -> None:
    existing = _ok(s.get(f"{HQ_URL}/api/v1/groups", timeout=15), "list groups")
    names = {g["name"] for g in existing.get("items", [])}
    if GROUP_NAME not in names:
        _ok(
            s.post(f"{HQ_URL}/api/v1/groups", json={"name": GROUP_NAME}, timeout=15),
            "create group",
        )
        print(f"[provision] created group {GROUP_NAME}")
    group = _ok(
        s.patch(
            f"{HQ_URL}/api/v1/groups/{GROUP_NAME}", json={"roles": [ROLE_NAME]}, timeout=15
        ),
        "attach role to group",
    )
    if ROLE_NAME not in {r["name"] for r in group.get("roles", [])}:
        _die(f"role {ROLE_NAME} did not attach to group {GROUP_NAME}")
    print(f"[provision] group {GROUP_NAME} -> role {ROLE_NAME}")


def ensure_service_account(s: Session) -> str:
    existing = _ok(
        s.get(f"{HQ_URL}/api/v1/service-accounts", timeout=15), "list service accounts"
    )
    names = {a["name"] for a in existing.get("items", [])}

    if SA_NAME in names:
        # HQ returns a token only when the account is created, so an existing
        # account has to be re-issued one. This invalidates the previous token
        # - anything still holding it starts getting 401s.
        body = _ok(
            # json={} rather than a bare POST: with no body there is no
            # Content-Type, and HQ answers 415 Unsupported Media Type.
            s.post(
                f"{HQ_URL}/api/v1/service-accounts/{SA_NAME}/renew-token",
                json={},
                timeout=15,
            ),
            "renew service-account token",
        )
        print(f"[provision] renewed token for existing account {SA_NAME}")
    else:
        body = _ok(
            s.post(
                f"{HQ_URL}/api/v1/service-accounts", json={"name": SA_NAME}, timeout=15
            ),
            "create service account",
        )
        print(f"[provision] created service account {SA_NAME}")

    token = body.get("token")
    if not token:
        _die(f"HQ returned no token for {SA_NAME}: {json.dumps(body)[:200]}")

    # THE step that matters. See the module docstring - the obvious spelling
    # of this returns 200 and does nothing.
    sa = _ok(
        s.put(
            f"{HQ_URL}/api/v1/service-accounts/{SA_NAME}/groups",
            json={"set_groups": [GROUP_NAME]},
            timeout=15,
        ),
        "set service-account groups",
    )
    joined = {g["name"] for g in sa.get("groups", [])}
    if GROUP_NAME not in joined:
        _die(
            f"{SA_NAME} is in groups {sorted(joined)} - expected {GROUP_NAME}. "
            "Without a group the token authenticates but sees nothing."
        )
    print(f"[provision] {SA_NAME} -> group {GROUP_NAME}")
    return token


def verify(s: Session, token: str) -> None:
    """Prove the token sees what an administrator sees.

    A token that authenticates but returns an empty environment list is the
    silent failure this script exists to prevent, so check for it here rather
    than letting the MCP server report "0 tools" much later.

    The comparison against the ADMIN view is what makes the check meaningful.
    `make up` provisions immediately after starting HQ, before the Lenses
    agent has registered its cluster, so "no environments" is the normal
    state at that moment - treating it as a permissions failure would break
    a clean-slate boot. Only a token that sees FEWER environments than admin
    has a real problem.
    """
    r = Session().get(
        f"{HQ_URL}/api/v1/environments",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if r.status_code != 200:
        _die(f"token rejected by HQ ({r.status_code})")
    sa_envs = {e.get("name") for e in r.json().get("items", [])}

    admin_envs = {
        e.get("name")
        for e in _ok(
            s.get(f"{HQ_URL}/api/v1/environments", timeout=15), "list environments"
        ).get("items", [])
    }

    if not admin_envs:
        print(
            "[provision] verified: token accepted by HQ. No environments are "
            "registered yet (the Lenses agent is still starting) - nothing "
            "to compare against."
        )
        return

    missing = admin_envs - sa_envs
    if missing:
        _die(
            f"token sees {sorted(sa_envs)} but admin sees {sorted(admin_envs)}. "
            "The group/role binding did not take effect - the account would "
            "authenticate and then see nothing."
        )
    print(
        f"[provision] verified: token sees all {len(sa_envs)} environment(s): "
        f"{', '.join(sorted(sa_envs))}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--write",
        action="store_true",
        help=f"also write the token to {CRED_FILE.relative_to(REPO_ROOT)} for compose",
    )
    args = ap.parse_args()

    print(f"[provision] HQ: {HQ_URL} (as {HQ_USER})")
    s = login()
    ensure_role(s)
    ensure_group(s)
    token = ensure_service_account(s)
    verify(s, token)

    if args.write:
        CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
        CRED_FILE.write_text(f"LENSES_API_KEY={token}\n", encoding="utf-8")
        CRED_FILE.chmod(0o600)
        print(f"[provision] wrote {CRED_FILE.relative_to(REPO_ROOT)} (mode 600)")
    else:
        print()
        print("  LENSES_API_KEY=" + token)
        print()
        print("  Re-run with --write to place it where compose can read it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
