# cards-ci-workflows

Reusable GitHub Actions workflows for the Cards & Payments repositories.
Owned by Cards Platform (`@dss26-org/cards-platform`).

| Workflow | What it does |
|---|---|
| [`schema-compat.yml`](.github/workflows/schema-compat.yml) | Fails a pull request whose Avro schema change is not `BACKWARD` compatible with the base branch |
| [`java-build.yml`](.github/workflows/java-build.yml) | Maven build and unit tests on Temurin, with the Maven cache |

The repository's Actions access is set to *Accessible from repositories in
the dss26-org organization*, so private repos in the org can call these
workflows.

## schema-compat

[INC-2024-09-12-003](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980001323/INC-2024-09-12-003+Incompatible+schema+on+cards.clearing.matched.v1):
a producer registered a schema on `cards.clearing.matched.v1` that the
clearing consumers could not read, and they stopped. The action item was a
schema compatibility check in CI for every cards repo. This is that check.

How it works:

1. Kafka and Schema Registry start as service containers - a throwaway
   registry, nothing shared with dev or prod.
2. For each `<subject>=<path>` pair, the version of the file on the base
   branch is registered under the subject.
3. The pull request's version is checked with
   `POST /compatibility/subjects/<subject>/versions/latest` at `BACKWARD`,
   the level every cards subject uses (schema evolution policy; declared per
   subject in `kafka-platform`).
4. An incompatible schema fails the job, with the registry's reasons as an
   annotation on the `.avsc` file and a table in the job summary.

A schema that does not exist on the base branch is new and passes.

### Calling it

```yaml
jobs:
  schema-compat:
    uses: dss26-org/cards-ci-workflows/.github/workflows/schema-compat.yml@main
    with:
      schemas: |
        cards.authorisation.requested.v1-value=src/main/avro/cards.authorisation.requested.v1.avsc
```

`schemas` takes one `<subject>=<path>` pair per line. The subject is
`<topic>-value` (one subject per topic, ADR-0007); the path is relative to
your repository root. Make `schema-compat / Avro schema compatibility` a
required status check on `main`.

Not supported yet: schemas that reference types from another subject.

### Who calls it

| Repository | Squad | Since |
|---|---|---|
| `merchant-gateway` | payments-edge | 2024-10 |
| `fraud-decisioning-svc` | cards-platform | 2024-10 |
| `clearing-settlement-svc` | clearing-settlement | 2024-11 |
| `disputes-svc` | cards-servicing | 2024-11 |

### Running the check locally

Start any throwaway Schema Registry (the one in your service's
docker-compose is fine), then from your repository root:

```sh
SCHEMA_REGISTRY_URL=http://localhost:8081 \
python3 path/to/cards-ci-workflows/.github/actions/schema-compat/schema_compat.py \
  --base-ref origin/main \
  --schemas 'cards.clearing.matched.v1-value=src/main/avro/cards.clearing.matched.v1.avsc'
```

Never point it at a shared registry: it registers the base versions it
compares against.

## Changing these workflows

Callers use `@main`, so a merge here changes every caller's CI straight away.
Try a change on a branch first by pointing one caller at `@<your-branch>`.
`ci.yml` runs actionlint and the tests, once without and once with a real
Schema Registry.

## Owners

Cards Platform - Slack `#cards-platform`.
