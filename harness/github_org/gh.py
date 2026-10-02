"""Minimal GitHub REST client (stdlib only).

Stdlib on purpose, so the scenario engine runs on the host under any python3,
without the repo's venv.

Token resolution, most specific first:

* ``GITHUB_SCENARIO_TOKEN`` - a token that can WRITE to the org's repos
  (contents + pull requests). This is the stage machinery's credential.
* ``GH_TOKEN``
* ``gh auth token`` - the host developer's CLI login, asked for with
  ``GITHUB_TOKEN`` unset (gh would otherwise just echo that variable).

``GITHUB_TOKEN`` is deliberately NOT used: in this repo it is the agent's
read-only token, and borrowing it here would turn every write into a
confusing 403/404.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")


class GitHubError(RuntimeError):
    def __init__(self, status: int, method: str, path: str, body: str):
        self.status = status
        super().__init__(f"GitHub {method} {path} -> HTTP {status}: {body[:700]}")


def _find_token() -> tuple[Optional[str], Optional[str]]:
    """``(token, where it came from)``, or ``(None, None)``."""
    for var in ("GITHUB_SCENARIO_TOKEN", "GH_TOKEN"):
        value = os.environ.get(var, "").strip()
        if value:
            return value, var
    if shutil.which("gh"):
        # gh answers with GITHUB_TOKEN when it is set, ahead of its stored
        # login - and the induce/reset scripts export the env file, where
        # GITHUB_TOKEN is the agent's read-only token. Ask for the login.
        env = {k: v for k, v in os.environ.items()
               if k not in ("GITHUB_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_ENTERPRISE_TOKEN")}
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, env=env)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip(), "`gh auth token`"
    return None, None


def resolve_token(required: bool = True) -> Optional[str]:
    token, _ = _find_token()
    if token:
        return token
    if required:
        raise RuntimeError(
            "No GitHub write token: set GITHUB_SCENARIO_TOKEN (contents + pull requests "
            "read/write on the org), or log in with `gh auth login`."
        )
    return None


class GitHub:
    def __init__(self, token: Optional[str] = None, api: str = API):
        self.token, self.token_source = (token, "the token passed in") if token else _find_token()
        if not self.token:
            resolve_token()  # raises with the setup hint
        self.api = api

    # -- transport -----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        params: Optional[dict] = None,
        accept: str = "application/vnd.github+json",
        allow: tuple[int, ...] = (),
        raw: bool = False,
    ) -> tuple[int, Any]:
        url = path if path.startswith("http") else f"{self.api}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dss26-org-seeder",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(6):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw_body = resp.read().decode()
                    status = resp.status
            except urllib.error.HTTPError as exc:
                raw_body = exc.read().decode()
                status = exc.code
                # Secondary rate limits (403/429 with Retry-After) and transient
                # 5xx are worth waiting out; everything else is the caller's.
                retry_after = exc.headers.get("Retry-After")
                limited = status in (403, 429) and (
                    retry_after or "secondary rate limit" in raw_body.lower()
                )
                if (limited or status >= 500) and attempt < 5:
                    time.sleep(int(retry_after or 0) or 2 ** attempt)
                    continue
                if status in allow:
                    return status, raw_body if raw else _maybe_json(raw_body)
                if status == 403 and "not accessible by personal access token" in raw_body:
                    # A fine-grained PAT that is read-only, or not granted this
                    # repo. Name the variable: the fallback chain hides which
                    # token was used, and the agent's own token is read-only.
                    raw_body += (
                        f" -- the token from {self.token_source} cannot write here. "
                        "Grant it Contents + Pull requests read/write on this repo "
                        "(fine-grained tokens list their repositories)"
                        + ("." if self.token_source == "`gh auth token`"
                           else ", or unset it to fall back to `gh auth token`.")
                    )
                raise GitHubError(status, method, path, raw_body) from None
            except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
                # Dropped connections (RemoteDisconnected, resets, timeouts)
                # are transient on a conference network - retry them too.
                if attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"GitHub unreachable: {exc}") from exc
            return status, raw_body if raw else _maybe_json(raw_body)
        raise RuntimeError("unreachable")

    def get(self, path, **kw):
        return self.request("GET", path, **kw)[1]

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body=body, **kw)[1]

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body=body, **kw)[1]

    def patch(self, path, body=None, **kw):
        return self.request("PATCH", path, body=body, **kw)[1]

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)[1]

    # -- helpers -------------------------------------------------------------

    def exists(self, path: str) -> bool:
        status, _ = self.request("GET", path, allow=(404,))
        return status != 404

    def read_file(self, owner: str, repo: str, path: str, ref: str = "main") -> Optional[str]:
        """Raw file text on ``ref``, or None when the file does not exist."""
        status, body = self.request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}",
            params={"ref": ref},
            accept="application/vnd.github.raw+json",
            allow=(404,),
            raw=True,
        )
        return None if status == 404 else body

    def basic_auth_header(self) -> str:
        """``http.extraHeader`` value for git over HTTPS with this token."""
        raw = base64.b64encode(f"x-access-token:{self.token}".encode()).decode()
        return f"Authorization: Basic {raw}"


def _maybe_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw
