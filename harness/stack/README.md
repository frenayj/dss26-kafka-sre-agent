# harness/stack/

The Docker Compose stack and the harness images it builds. Use `make up` from
the repo root: it provisions the Lenses service account between starting HQ
and starting everything else.

The stack runs both sides of the repo: the harness (cluster, Lenses, the
fraud-decisioning consumer, the seeder) and the agent (agent server,
dashboard, LLM gateway, Phoenix). The agent's images are built from their own
folders: [`agent/Dockerfile`](../../agent/Dockerfile) and
[`ui/Dockerfile`](../../ui/Dockerfile).

| File | What it is |
|---|---|
| `docker-compose.yml` | The whole stack |
| `fast-data-dev.Dockerfile` | The Kafka cluster image, plus kafka-connect-datagen for baseline traffic |
| `datagen/` | The datagen template for card-authorisation events |
| `seeder.Dockerfile` | One-shot container that runs [`../seed/`](../seed): topics, schemas, metadata, the datagen producer |
| `schemas/` | Avro schemas: authorisation v1, the breaking v2 the consumer-lag scenario registers, ledger posting |
| `fraud_scoring/` | The fraud-decisioning consumer the consumer-lag incident wedges |
| `patches/` | Two Lenses MCP source files mounted over the image's copies (see below) |
| `preflight.sh` | `make preflight`: env file, services, endpoints and gateway in one check |
| `sa-credentials.conf` | Written by `make provision`; git-ignored |

## Services and ports

| Service | Host port | |
|---|---|---|
| `ui` | 8080 | Dashboard |
| `agent-server` | 8765 | Agent API (SSE) |
| `llm-gateway` | 4000 | LiteLLM |
| `phoenix` | 6006 | Traces |
| `lenses-hq` | 9991 | Lenses HQ (`admin` / `admin`) |
| `lenses-mcp` | 8000 | Lenses MCP server |
| `lenses-agent-prod` | | Attaches the cluster to HQ as `cards-prod-euw1` |
| `demo-kafka-prod` | 9092, 8081, 8093 | Broker, Schema Registry, Kafka Connect |
| `fraud-decisioning-engine` | | Consumer of `cards.authorisation.requested.v1` |
| `postgres`, `create-configs`, `seeder` | | Supporting and one-shot services |

Every host port can be moved with a `HOST_PORT_*` variable
(`ports.parallel.sample` at the repo root sets a full alternative set). In
the network, the broker is `demo-kafka-prod:19092`, Schema Registry `:8081`
and Connect `:8083`.

## Notes

**Lenses MCP patch.** mcp 6.2's HTTP client always sends
`Accept: application/json`, but the connector-definition endpoint only
serves YAML (HTTP 415), so `get_kafka_connector_target_definition` fails.
`patches/` holds full copies of the two affected files with the fix, which
is why the image is pinned to a digest: re-derive the patches whenever the
digest changes, and drop them once an image ships the fix.

**Postgres keeps no data volume**, so `make down` wipes HQ's database (users,
service accounts, environments). `make up` re-provisions everything.
