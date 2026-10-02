# Troubleshooting

`make preflight` checks the env file, the services and the gateway in one go.
Start there.

**Lenses HQ won't start.** Set `ACCEPT_EULA=true` in `.env`. Without
`--env-file .env` (which `make` passes for you) compose looks for
`harness/stack/.env` instead, and every variable resolves to empty.

**`lenses-mcp` exits on first boot.** It needs the service-account key that
`make provision` writes to `harness/stack/sa-credentials.conf` once HQ is up. `make
up` does both in order; a bare `docker compose up` doesn't. Run `make
provision`, then `make up`.

**A run fails straight away with a provider error.** The gateway has no key
for the model the role uses. Add `ANTHROPIC_API_KEY` (or the key for the
alias you picked) to `.env`, then `make gateway-up`.

**A port is already taken.** Copy `ports.parallel.sample` to
`ports.parallel`: it moves the host ports that usually clash (broker, Schema
Registry, Connect, HQ, MCP, Phoenix) to 1xxxx equivalents. Delete it to go
back.

**Phoenix shows $0.00.** Pricing is applied when a span is ingested, so only
traces recorded after `make phoenix-costs` have a cost. `make up` runs it;
re-run it after `make clean`. If a trace seems missing, check Phoenix's
project selector: runs land in `kafka-sre-agent`, not `default`.

**`make induce` says `WARN: GitHub path failed`.** Only relevant with
`GITHUB_MODE=live`. The script couldn't write to the org, so it broke the
cluster from the local files and there is no culprit PR to find. The
`github>` lines above the warning say why; a `403 … not accessible by
personal access token` names the token it used. See
[the GitHub org](github-org.md#seeding-your-own-org).

**The agent asks for a Lenses sign-in.** That only happens without a
service-account key (for example a host run with `OAUTH_ENABLED=true` on
`lenses-mcp`). Open the URL it prints and sign in as `admin` / `admin`. If
the authorize URL answers 404, HQ has forgotten the agent's OAuth client
(HQ's database doesn't survive `make down`). Clear the agent's cached
registration and restart it, then use the fresh URL from its logs:

```sh
docker exec dss26-agent-server-1 \
  python3 -c "import json; json.dump({}, open('/data/cache/kafka-sre-agent/oauth.json','w'))"
docker restart dss26-agent-server-1
```

On the host the cache is `~/.cache/kafka-sre-agent/oauth.json`.

**Everything is slow or containers get killed.** The stack needs roughly
8 GB of memory available to Docker.
