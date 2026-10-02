# Service accounts and ACLs

Every service that talks to a cards cluster has its own principal. People do
not get Kafka credentials: they use Lenses with their SSO group, and write
access there is time-boxed and approved.

## Naming

`svc-<service>`, where `<service>` is the deployable's name without the
`-svc` suffix: `svc-merchant-gateway`, `svc-fraud-decisioning`. The file is
`acls/svc-<service>.yaml` and the Kafka principal is `User:svc-<service>`.

Kafka Connect sinks get one principal per connector, named after what the
connector does and ending in `-connect` (`svc-disputes-search-connect`). The
Connect workers run with `connector.client.config.override.policy=Principal`,
so each connector authenticates as its own account and its consumer group is
`connect-<connector-name>`.

## Credentials

SCRAM-SHA-512 credentials are created by Platform Engineering when the file is
merged and written to Vault at `kv/kafka/<cluster>/<service-account>`. The
service reads them from there at deploy time; nobody copies them by hand.
Rotation is every 60 days and does not need a change here.

## Writing ACLs

```yaml
service_account: svc-txn-history-builder
owner: cards-servicing
description: >-
  txn-history-builder - cardholder transaction history for the mobile and
  internet banking apps.
clusters:
  - cards-prod-euw1
  - cards-dev-euw1
acls:
  - resource: topic
    name: cards.authorisation.requested.v1
    pattern: literal
    operations: [READ, DESCRIBE]
  - resource: group
    name: txn-history-builder
    pattern: literal
    operations: [READ]
```

- Grant the topics a service reads or writes **literally**. Prefixed topic
  grants are for a service's own internal topics (Kafka Streams changelogs and
  repartition topics share the `application.id` prefix) and may not cover a
  catalogue topic.
- A consumer needs `READ` on its topics and `READ` on its consumer group.
- A producer needs `WRITE` and `DESCRIBE` on its topics; idempotent producers
  on older clients also need `IDEMPOTENT_WRITE` on `kafka-cluster`.
- Exactly-once Kafka Streams applications also need `WRITE` and `DESCRIBE` on
  `transactional_id`, prefixed with the `application.id`.
- One consumer group per service. If you run two versions side by side during
  a rollout, use a prefixed group grant rather than sharing a group.

## Read-only accounts

Wildcard grants (`name: "*"`) are only allowed for read operations - `READ`,
`DESCRIBE` and `DESCRIBE_CONFIGS` - and `validate` rejects anything else.
They are for tooling that has to see the whole estate, such as the SRE
on-call tooling (`svc-sre-agent`). A read-only account never joins a consumer
group, so it does not get group `READ`: `DESCRIBE` on groups is enough to see
members and offsets.

## Removing access

Delete the file or the ACL entry and merge. `apply` does not delete ACLs; the
plan lists them as unmanaged and Platform Engineering removes them under a
PLAT ticket.
