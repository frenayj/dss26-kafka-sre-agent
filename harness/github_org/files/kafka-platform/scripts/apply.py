#!/usr/bin/env python3
"""Plan or apply the definitions in this repo to one Kafka cluster.

    python3 scripts/apply.py --cluster cards-dev-euw1 --plan
    python3 scripts/apply.py --cluster cards-dev-euw1

What it changes, for the topics and service accounts that list the cluster:

* creates missing topics, and raises partition counts (never lowers them -
  Kafka cannot shrink a topic, and doing it by hand reorders keys);
* sets the topic configs declared under ``config``;
* sets each Avro subject's compatibility level in the cluster's Schema Registry;
* creates missing ALLOW ACLs for each service account.

It never deletes. A topic or ACL in the cluster that git does not declare is
listed as unmanaged; removing it is a manual change with a PLAT ticket.

Credentials come from the environment (the runner reads them from Vault):
KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD and SCHEMA_REGISTRY_USER_INFO.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from validate import ROOT, Definitions, load, validate

CLIENT_ID = "kafka-platform-apply"
TIMEOUT_S = 30


@dataclass(frozen=True, order=True)
class Binding:
    """One ALLOW ACL, in the shape both git and the cluster can be read into."""

    principal: str
    resource: str  # topic | group | cluster | transactional_id
    name: str
    pattern: str  # literal | prefixed
    operation: str

    def __str__(self) -> str:
        return (f"{self.principal} {self.operation} on {self.resource} "
                f"{self.name}{'*' if self.pattern == 'prefixed' else ''}")


@dataclass(frozen=True)
class Change:
    kind: str
    target: str
    detail: str
    payload: Any = field(default=None, compare=False)

    def __str__(self) -> str:
        return f"{self.kind:<18} {self.target}  {self.detail}"


# ---------------------------------------------------------------------------
# Desired state, from git
# ---------------------------------------------------------------------------


def desired_topics(defs: Definitions, cluster: str) -> dict[str, dict]:
    return {
        str(doc["name"]): doc
        for doc in defs.topics.values()
        if cluster in (doc.get("clusters") or ())
    }


def desired_bindings(defs: Definitions, cluster: str) -> set[Binding]:
    out: set[Binding] = set()
    for doc in defs.accounts.values():
        if cluster not in (doc.get("clusters") or ()):
            continue
        principal = f"User:{doc['service_account']}"
        for acl in doc.get("acls") or ():
            for operation in acl["operations"]:
                out.add(Binding(principal, acl["resource"], acl["name"],
                                acl.get("pattern", "literal"), operation))
    return out


# ---------------------------------------------------------------------------
# Planning - pure functions, unit tested
# ---------------------------------------------------------------------------


def plan_topics(
    desired: dict[str, dict],
    partitions: dict[str, int],
    configs: dict[str, dict[str, str]],
) -> list[Change]:
    """Changes that bring topics and their configs in line with git."""
    changes: list[Change] = []
    for name, doc in sorted(desired.items()):
        wanted_config = {k: str(v) for k, v in (doc.get("config") or {}).items()}
        if name not in partitions:
            changes.append(Change(
                "create-topic", name,
                f"partitions={doc['partitions']} replication_factor={doc['replication_factor']}",
                payload=(doc["partitions"], doc["replication_factor"], wanted_config),
            ))
            continue
        if doc["partitions"] > partitions[name]:
            changes.append(Change(
                "add-partitions", name, f"{partitions[name]} -> {doc['partitions']}",
                payload=doc["partitions"],
            ))
        elif doc["partitions"] < partitions[name]:
            changes.append(Change(
                "skip", name,
                f"git declares {doc['partitions']} partitions, cluster has "
                f"{partitions[name]} - partitions are never removed",
            ))
        current = configs.get(name, {})
        drift = {k: v for k, v in wanted_config.items() if current.get(k) != v}
        if drift:
            detail = ", ".join(f"{k}: {current.get(k)} -> {v}" for k, v in sorted(drift.items()))
            changes.append(Change("set-config", name, detail, payload=drift))
    return changes


def plan_compatibility(desired: dict[str, dict], current: dict[str, str | None]) -> list[Change]:
    """Subject-level compatibility, so a subject never falls back to the global default."""
    changes: list[Change] = []
    for _, doc in sorted(desired.items()):
        schema = doc.get("schema")
        if doc.get("value_format") != "avro" or not schema:
            continue
        subject, level = schema["subject"], schema["compatibility"]
        if current.get(subject) != level:
            changes.append(Change(
                "set-compatibility", subject, f"{current.get(subject) or 'global default'} -> {level}",
                payload=level,
            ))
    return changes


def plan_acls(desired: set[Binding], existing: set[Binding]) -> tuple[list[Change], list[Binding]]:
    """ACLs to create, and the ones in the cluster that git does not declare."""
    create = [Change("create-acl", b.principal, str(b).removeprefix(f"{b.principal} "), payload=b)
              for b in sorted(desired - existing)]
    unmanaged = sorted(existing - desired)
    return create, unmanaged


# ---------------------------------------------------------------------------
# Reading and writing the cluster
# ---------------------------------------------------------------------------


def admin_client(cluster: dict):
    from confluent_kafka.admin import AdminClient

    conf = {"bootstrap.servers": cluster["bootstrap_servers"], "client.id": CLIENT_ID}
    protocol = cluster.get("security_protocol", "PLAINTEXT")
    if protocol != "PLAINTEXT":
        conf.update({
            "security.protocol": protocol,
            "sasl.mechanism": cluster.get("sasl_mechanism", "SCRAM-SHA-512"),
            "sasl.username": os.environ["KAFKA_SASL_USERNAME"],
            "sasl.password": os.environ["KAFKA_SASL_PASSWORD"],
        })
    return AdminClient(conf)


def read_topics(admin, names: set[str]) -> tuple[dict[str, int], dict[str, dict[str, str]]]:
    from confluent_kafka.admin import ConfigResource, ResourceType

    metadata = admin.list_topics(timeout=TIMEOUT_S)
    partitions = {
        name: len(topic.partitions)
        for name, topic in metadata.topics.items()
        if not name.startswith("_")
    }
    resources = [ConfigResource(ResourceType.TOPIC, n) for n in sorted(names & partitions.keys())]
    configs: dict[str, dict[str, str]] = {}
    if resources:
        for resource, future in admin.describe_configs(resources).items():
            configs[resource.name] = {k: e.value for k, e in future.result().items()}
    return partitions, configs


_RESOURCE_TYPES = {"topic": "TOPIC", "group": "GROUP", "cluster": "BROKER",
                   "transactional_id": "TRANSACTIONAL_ID"}


def read_acls(admin) -> set[Binding]:
    from confluent_kafka.admin import (
        AclBindingFilter, AclOperation, AclPermissionType, ResourcePatternType, ResourceType,
    )

    names = {v: k for k, v in _RESOURCE_TYPES.items()}
    flt = AclBindingFilter(ResourceType.ANY, None, ResourcePatternType.ANY, None, None,
                           AclOperation.ANY, AclPermissionType.ANY)
    out: set[Binding] = set()
    for acl in admin.describe_acls(flt).result(timeout=TIMEOUT_S):
        if acl.permission_type != AclPermissionType.ALLOW or acl.restype.name not in names:
            continue
        out.add(Binding(acl.principal, names[acl.restype.name], acl.name,
                        acl.resource_pattern_type.name.lower(), acl.operation.name))
    return out


def _registry(url: str, path: str, body: dict | None = None) -> dict | None:
    req = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method="PUT" if body is not None else "GET",
        headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
    )
    user_info = os.environ.get("SCHEMA_REGISTRY_USER_INFO")
    if user_info:
        req.add_header("Authorization", "Basic " + base64.b64encode(user_info.encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and body is None:
            return None  # no subject-level setting
        raise


def read_compatibility(url: str, subjects: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for subject in subjects:
        doc = _registry(url, f"/config/{urllib.parse.quote(subject, safe='')}?defaultToGlobal=false")
        out[subject] = (doc or {}).get("compatibilityLevel")
    return out


def execute(admin, cluster: dict, changes: list[Change]) -> None:
    from confluent_kafka.admin import (
        AclBinding, AclOperation, AclPermissionType, AlterConfigOpType, ConfigEntry,
        ConfigResource, NewPartitions, NewTopic, ResourcePatternType, ResourceType,
    )

    for change in changes:
        print(f"applying  {change}")
        if change.kind == "create-topic":
            parts, rf, config = change.payload
            futures = admin.create_topics([NewTopic(change.target, num_partitions=parts,
                                                    replication_factor=rf, config=config)])
        elif change.kind == "add-partitions":
            futures = admin.create_partitions([NewPartitions(change.target, change.payload)])
        elif change.kind == "set-config":
            entries = [ConfigEntry(k, v, incremental_operation=AlterConfigOpType.SET)
                       for k, v in change.payload.items()]
            resource = ConfigResource(ResourceType.TOPIC, change.target, incremental_configs=entries)
            futures = admin.incremental_alter_configs([resource])
        elif change.kind == "set-compatibility":
            subject = urllib.parse.quote(change.target, safe="")
            _registry(cluster["schema_registry_url"], f"/config/{subject}",
                      {"compatibility": change.payload})
            continue
        elif change.kind == "create-acl":
            b: Binding = change.payload
            futures = admin.create_acls([AclBinding(
                getattr(ResourceType, _RESOURCE_TYPES[b.resource]), b.name,
                getattr(ResourcePatternType, b.pattern.upper()), b.principal, "*",
                getattr(AclOperation, b.operation), AclPermissionType.ALLOW,
            )])
        else:
            continue
        for future in futures.values():
            future.result()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cluster", required=True)
    ap.add_argument("--plan", action="store_true", help="print the changes, apply nothing")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)

    defs = load(Path(args.root).resolve())
    problems = validate(defs)
    if problems:
        for problem in problems:
            print(problem.annotation(defs.root))
        print("refusing to apply: scripts/validate.py reports problems")
        return 1
    if args.cluster not in defs.clusters:
        print(f"unknown cluster {args.cluster!r}; known: {', '.join(sorted(defs.clusters))}")
        return 2
    cluster = defs.clusters[args.cluster]

    topics = desired_topics(defs, args.cluster)
    admin = admin_client(cluster)
    partitions, configs = read_topics(admin, set(topics))
    changes = plan_topics(topics, partitions, configs)
    if cluster.get("schema_registry_url"):
        subjects = sorted(d["schema"]["subject"] for d in topics.values() if d.get("schema"))
        changes += plan_compatibility(topics, read_compatibility(cluster["schema_registry_url"], subjects))
    acl_changes, unmanaged = plan_acls(desired_bindings(defs, args.cluster), read_acls(admin))
    changes += acl_changes

    print(f"plan for {args.cluster}: {len(changes)} change(s)")
    for change in changes:
        print(f"  {change}")
    for name in sorted(set(partitions) - set(topics)):
        print(f"  unmanaged topic    {name}")
    for binding in unmanaged:
        print(f"  unmanaged acl      {binding}")
    if args.plan:
        return 0
    execute(admin, cluster, [c for c in changes if c.kind != "skip"])
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
