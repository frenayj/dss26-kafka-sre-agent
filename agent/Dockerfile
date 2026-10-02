# Kafka SRE Agent - the FastAPI server, plus the stdio MCP servers it spawns
# as child processes: its own Confluence and Slack servers, GitHub's official
# server (live), or the harness's offline test doubles (stub). PagerDuty's
# hosted MCP server and Lenses MCP are reached over the network.
#
# Build context is the REPO ROOT (so `agent/` is importable as a package and
# REPO_ROOT resolves to /app). See harness/stack/docker-compose.yml → agent-server.
FROM python:3.12-slim

WORKDIR /app

# Install deps first so the layer caches across code edits.
COPY agent/requirements.txt agent/requirements.txt
RUN pip install --no-cache-dir -r agent/requirements.txt

# GitHub's official MCP server - the live back-end of the forensics agent's
# GitHub tools (GITHUB_MODE=live), spawned over stdio like the stubs. Pinned,
# and verified against the release's checksum file before it is installed.
ARG GITHUB_MCP_VERSION=1.12.2
ARG TARGETARCH
RUN python - <<'EOF'
import hashlib, io, os, tarfile, urllib.request
version = os.environ.get("GITHUB_MCP_VERSION", "1.12.2")
arch = {"amd64": "x86_64", "arm64": "arm64"}[os.environ.get("TARGETARCH") or "amd64"]
base = f"https://github.com/github/github-mcp-server/releases/download/v{version}"
asset = f"github-mcp-server_Linux_{arch}.tar.gz"
blob = urllib.request.urlopen(f"{base}/{asset}", timeout=120).read()
sums = urllib.request.urlopen(f"{base}/github-mcp-server_{version}_checksums.txt", timeout=60).read().decode()
expected = next(line.split()[0] for line in sums.splitlines() if line.endswith(asset))
assert hashlib.sha256(blob).hexdigest() == expected, "github-mcp-server checksum mismatch"
with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
    member = tar.getmember("github-mcp-server")
    with open("/usr/local/bin/github-mcp-server", "wb") as out:
        out.write(tar.extractfile(member).read())
os.chmod("/usr/local/bin/github-mcp-server", 0o755)
EOF

# Application code. agent/ holds the server, sub-agents, prompts, skills,
# MCP servers and the OAuth client - everything the process needs at runtime.
COPY agent/ agent/
# The offline test doubles (stub mode) and the scenarios' alerts they serve.
# Only spawned, never imported: see agent/mcp_clients.py.
COPY harness/__init__.py harness/__init__.py
COPY harness/stubs/ harness/stubs/
COPY harness/scenarios/ harness/scenarios/

# Persistent state on a named volume: the OAuth token cache
# (XDG_CACHE_HOME/kafka-sre-agent/oauth.json) so the one-time Lenses login
# survives restarts, plus the SQLite run history.
ENV XDG_CACHE_HOME=/data/cache \
    AGENT_DB_PATH=/data/runs.db \
    AGENT_PORT=8765
RUN mkdir -p /data/cache
VOLUME ["/data"]

EXPOSE 8765

# /ping answers 200 both while waiting for the one-time OAuth login
# (status=needs_auth, served by the temporary callback server) and once the
# agent is fully up (status=healthy) - so this reflects "process is alive".
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8765/ping')"]

CMD ["python", "-m", "agent.server"]
