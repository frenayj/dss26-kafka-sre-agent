#!/usr/bin/env python3
"""Validate the Kafka platform definitions before they are merged.

Reads teams.yaml, clusters/, topics/ and acls/ and checks them against the
platform rules described in README.md: topic naming, required keys, known
owners and clusters, replication settings, Schema Registry subjects and
compatibility, and service-account ACLs.

Problems are printed as GitHub workflow annotations, so they show inline on
the pull request. Exit status is 1 if there is at least one problem.

    python3 scripts/validate.py [--root PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import yaml

ROOT = Path(__file__).resolve().parent.parent

# <domain>.<entity>.<event>.v<N>: lower case, dots between the parts, hyphens
# inside a part. The version is part of the name - a breaking change to the
# payload is a new topic, not a new schema version. Dead-letter topics append
# ".dlq" to the name of the topic they serve.
TOPIC_NAME = re.compile(
    r"^(?P<domain>[a-z]+)(\.[a-z][a-z0-9-]*){2,}\.v[1-9][0-9]*(?P<dlq>\.dlq)?$"
)
SERVICE_ACCOUNT = re.compile(r"^svc-[a-z0-9]+(-[a-z0-9]+)*$")

TIERS = ("tier-1", "tier-2", "tier-3")
VALUE_FORMATS = ("avro", "json", "string", "bytes")
CLEANUP_POLICIES = ("delete", "compact", "compact,delete")
COMPATIBILITY = (
    "BACKWARD", "BACKWARD_TRANSITIVE", "FORWARD", "FORWARD_TRANSITIVE",
    "FULL", "FULL_TRANSITIVE", "NONE",
)
# Consumers of card events must keep reading after a producer upgrade
# (ADR-0007 and the schema evolution policy), so cards subjects are BACKWARD
# or stricter.
CARDS_COMPATIBILITY = ("BACKWARD", "BACKWARD_TRANSITIVE", "FULL", "FULL_TRANSITIVE")

CLUSTER_KEYS = ("name", "environment", "bootstrap_servers", "min_replication_factor")
TOPIC_KEYS = (
    "name", "owner", "tier", "description", "clusters", "partitions",
    "replication_factor", "config", "value_format",
)
ACCOUNT_KEYS = ("service_account", "owner", "description", "clusters", "acls")

OPERATIONS = {
    "topic": {"READ", "WRITE", "CREATE", "DELETE", "DESCRIBE", "DESCRIBE_CONFIGS", "ALTER_CONFIGS"},
    "group": {"READ", "DESCRIBE", "DELETE"},
    "cluster": {"DESCRIBE", "DESCRIBE_CONFIGS", "IDEMPOTENT_WRITE"},
    "transactional_id": {"WRITE", "DESCRIBE"},
}
PATTERNS = ("literal", "prefixed")
WRITE_OPERATIONS = {"WRITE", "CREATE", "DELETE", "ALTER_CONFIGS"}
READ_ONLY = {"READ", "DESCRIBE", "DESCRIBE_CONFIGS"}


@dataclass
class Problem:
    path: Path
    message: str

    def annotation(self, root: Path) -> str:
        try:
            where = self.path.relative_to(root)
        except ValueError:
            where = self.path
        return f"::error file={where}::{self.message}"


@dataclass
class Definitions:
    root: Path
    teams: set[str] = field(default_factory=set)
    clusters: dict[str, dict[str, Any]] = field(default_factory=dict)
    topics: dict[Path, dict[str, Any]] = field(default_factory=dict)
    accounts: dict[Path, dict[str, Any]] = field(default_factory=dict)
    problems: list[Problem] = field(default_factory=list)

    @property
    def topic_names(self) -> set[str]:
        return {str(doc.get("name")) for doc in self.topics.values()}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _read(path: Path, problems: list[Problem]) -> dict[str, Any] | None:
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        problems.append(Problem(path, f"not valid YAML: {exc}".replace("\n", " ")))
        return None
    if not isinstance(doc, dict):
        problems.append(Problem(path, "expected a mapping at the top level"))
        return None
    return doc


def load(root: Path) -> Definitions:
    defs = Definitions(root=root)

    teams = _read(root / "teams.yaml", defs.problems) or {}
    defs.teams = {t["slug"] for t in teams.get("teams") or () if isinstance(t, dict) and "slug" in t}

    for path in sorted((root / "clusters").glob("*.yaml")):
        doc = _read(path, defs.problems)
        if doc is not None:
            defs.clusters[path.stem] = doc

    for path in sorted((root / "topics").rglob("*")):
        if path.is_dir():
            continue
        if path.suffix != ".yaml" or path.parent.parent != root / "topics":
            defs.problems.append(Problem(path, "topic files live in topics/<domain>/<topic>.yaml"))
            continue
        doc = _read(path, defs.problems)
        if doc is not None:
            defs.topics[path] = doc

    for path in sorted((root / "acls").glob("*")):
        if path.suffix != ".yaml":
            defs.problems.append(Problem(path, "service account files are acls/<service-account>.yaml"))
            continue
        doc = _read(path, defs.problems)
        if doc is not None:
            defs.accounts[path] = doc
    return defs


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------


def check_cluster(name: str, doc: dict[str, Any]) -> Iterator[str]:
    for key in CLUSTER_KEYS:
        if key not in doc:
            yield f"missing required key {key!r}"
    if doc.get("name") != name:
        yield f"name {doc.get('name')!r} does not match the file name {name!r}"
    if "min_replication_factor" in doc and not _positive_int(doc["min_replication_factor"]):
        yield "min_replication_factor must be a positive integer"


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

Check = Callable[[Definitions, Path, dict], Iterable[str]]


def check_required(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    for key in TOPIC_KEYS:
        if key not in doc:
            yield f"missing required key {key!r}"


def check_name(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    name = str(doc.get("name", ""))
    if path.name != f"{name}.yaml":
        yield f"file name must be {name}.yaml"
    match = TOPIC_NAME.match(name)
    if not match:
        yield f"topic name {name!r} does not follow <domain>.<entity>.<event>.v<N>"
    elif path.parent.name != match["domain"]:
        yield f"{name} belongs in topics/{match['domain']}/"


def check_owner(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    owner = doc.get("owner")
    if owner not in defs.teams:
        yield f"owner {owner!r} is not a team in teams.yaml"
    if doc.get("tier") not in TIERS:
        yield f"tier must be one of {', '.join(TIERS)}"
    if not str(doc.get("description") or "").strip():
        yield "description must not be empty - it is what the topic catalogue shows"


def check_placement(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    clusters = doc.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        yield "clusters must be a non-empty list"
        clusters = []
    for cluster in clusters:
        if cluster not in defs.clusters:
            yield f"unknown cluster {cluster!r} (see clusters/)"
    if not _positive_int(doc.get("partitions")):
        yield "partitions must be a positive integer"
    rf = doc.get("replication_factor")
    if not _positive_int(rf):
        yield "replication_factor must be a positive integer"
        return
    for cluster in clusters:
        minimum = defs.clusters.get(cluster, {}).get("min_replication_factor", 1)
        if _positive_int(minimum) and rf < minimum:
            yield f"replication_factor {rf} is below the minimum of {minimum} on {cluster}"


def check_config(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    config = doc.get("config")
    if not isinstance(config, dict):
        yield "config must be a mapping of topic configs"
        return
    if config.get("cleanup.policy") not in CLEANUP_POLICIES:
        yield f"config.cleanup.policy must be one of {', '.join(CLEANUP_POLICIES)}"
    retention = config.get("retention.ms")
    if not (_positive_int(retention) or retention == -1):
        yield "config.retention.ms must be a positive number of milliseconds (or -1)"
    isr = config.get("min.insync.replicas")
    rf = doc.get("replication_factor")
    if isr is not None and _positive_int(rf) and (not _positive_int(isr) or isr >= rf):
        yield "config.min.insync.replicas must be lower than replication_factor"
    if doc.get("value_format") not in VALUE_FORMATS:
        yield f"value_format must be one of {', '.join(VALUE_FORMATS)}"


def check_schema(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    """Avro topics declare their Schema Registry subject and compatibility (ADR-0007)."""
    name = str(doc.get("name", ""))
    schema = doc.get("schema")
    if doc.get("value_format") != "avro":
        if schema is not None:
            yield "schema is only used with value_format: avro"
        return
    if not isinstance(schema, dict):
        yield "avro topics need a schema block with subject and compatibility"
        return
    if schema.get("subject") != f"{name}-value":
        yield f"schema.subject must be {name}-value (one subject per topic, TopicNameStrategy)"
    level = schema.get("compatibility")
    if level not in COMPATIBILITY:
        yield f"schema.compatibility {level!r} is not a Schema Registry compatibility level"
    elif name.startswith("cards.") and level not in CARDS_COMPATIBILITY:
        yield f"cards subjects must be BACKWARD compatible or stricter, not {level}"
    elif doc.get("tier") == "tier-1" and level == "NONE":
        yield "tier-1 subjects cannot use compatibility NONE"


def check_tags(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    """Catalogue tags agree with the owner, tier and domain of the topic."""
    tags = doc.get("tags")
    if not isinstance(tags, list) or not tags:
        yield "tags must be a non-empty list"
        return
    for tag in tags:
        if not isinstance(tag, str) or ":" not in tag:
            yield f"tag {tag!r} is not key:value"
    expected = {
        f"domain:{path.parent.name}",
        f"owner:{doc.get('owner')}",
        f"criticality:{doc.get('tier')}",
        "data-residency:eu",
    }
    for tag in sorted(expected - set(map(str, tags))):
        yield f"missing tag {tag}"


def check_dead_letter(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    """A .dlq topic names the topic it serves, and lives next to it."""
    name = str(doc.get("name", ""))
    source = doc.get("dead_letter_for")
    if not name.endswith(".dlq"):
        if source is not None:
            yield "dead_letter_for is only valid on a .dlq topic"
        return
    if source != name.removesuffix(".dlq"):
        yield f"dead_letter_for must be {name.removesuffix('.dlq')}"
    elif source not in defs.topic_names:
        yield f"{source} is not declared under topics/"
    if doc.get("value_format") != "bytes":
        yield "dead-letter topics hold the original bytes: value_format must be bytes"


TOPIC_CHECKS: tuple[Check, ...] = (
    check_required,
    check_name,
    check_owner,
    check_placement,
    check_config,
    check_schema,
    check_tags,
    check_dead_letter,
)


# ---------------------------------------------------------------------------
# Service accounts and ACLs
# ---------------------------------------------------------------------------


def _acls(doc: dict) -> Iterator[tuple[int, dict]]:
    for i, acl in enumerate(doc.get("acls") or ()):
        if isinstance(acl, dict):
            yield i, acl


def check_account(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    for key in ACCOUNT_KEYS:
        if key not in doc:
            yield f"missing required key {key!r}"
    account = str(doc.get("service_account", ""))
    if not SERVICE_ACCOUNT.match(account):
        yield f"service account {account!r} must look like svc-<service>"
    if path.stem != account:
        yield f"file name must be {account}.yaml"
    if doc.get("owner") not in defs.teams:
        yield f"owner {doc.get('owner')!r} is not a team in teams.yaml"
    for cluster in doc.get("clusters") or ():
        if cluster not in defs.clusters:
            yield f"unknown cluster {cluster!r} (see clusters/)"
    if not isinstance(doc.get("acls"), list) or not doc["acls"]:
        yield "acls must be a non-empty list"


def check_acls(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    declared = defs.topic_names
    for i, acl in _acls(doc):
        where = f"acls[{i}]"
        resource, name = acl.get("resource"), acl.get("name")
        pattern = acl.get("pattern", "literal")
        operations = acl.get("operations")
        if resource not in OPERATIONS:
            yield f"{where}: resource must be one of {', '.join(OPERATIONS)}"
            continue
        if pattern not in PATTERNS:
            yield f"{where}: pattern must be literal or prefixed"
        if not isinstance(name, str) or not name:
            yield f"{where}: name is required"
            continue
        if not isinstance(operations, list) or not operations:
            yield f"{where}: operations must be a non-empty list"
            continue
        invalid = sorted(set(operations) - OPERATIONS[resource])
        if invalid:
            yield f"{where}: {', '.join(invalid)} not valid on a {resource}"
        if resource == "cluster" and name != "kafka-cluster":
            yield f"{where}: the cluster resource is always named kafka-cluster"
        if resource != "topic":
            continue
        if pattern == "literal" and name != "*" and name not in declared:
            yield f"{where}: topic {name} is not declared under topics/"
        if pattern == "prefixed" and WRITE_OPERATIONS & set(operations):
            covered = sorted(t for t in declared if t.startswith(name))
            if covered:
                yield (f"{where}: prefixed write access on {name!r} covers catalogue "
                       f"topics ({', '.join(covered[:3])}) - grant those literally")


def check_wildcards(defs: Definitions, path: Path, doc: dict) -> Iterator[str]:
    """A wildcard grant is read-only: nobody gets write access to everything."""
    for i, acl in _acls(doc):
        if acl.get("name") == "*" and not set(acl.get("operations") or ()) <= READ_ONLY:
            yield f"acls[{i}]: wildcard grants are read-only ({', '.join(sorted(READ_ONLY))})"


ACCOUNT_CHECKS: tuple[Check, ...] = (
    check_account,
    check_acls,
    check_wildcards,
)


# ---------------------------------------------------------------------------


def validate(defs: Definitions) -> list[Problem]:
    problems = list(defs.problems)
    for name, doc in defs.clusters.items():
        path = defs.root / "clusters" / f"{name}.yaml"
        problems.extend(Problem(path, msg) for msg in check_cluster(name, doc))

    seen: dict[str, Path] = {}
    for path, doc in defs.topics.items():
        for check in TOPIC_CHECKS:
            problems.extend(Problem(path, msg) for msg in check(defs, path, doc))
        name = str(doc.get("name"))
        if name in seen:
            problems.append(Problem(path, f"{name} is already declared in {seen[name].name}"))
        seen.setdefault(name, path)

    for path, doc in defs.accounts.items():
        for check in ACCOUNT_CHECKS:
            problems.extend(Problem(path, msg) for msg in check(defs, path, doc))
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    defs = load(root)
    problems = validate(defs)
    for problem in problems:
        print(problem.annotation(root))
    status = "OK" if not problems else f"{len(problems)} problem(s)"
    print(f"{len(defs.topics)} topics, {len(defs.accounts)} service accounts, "
          f"{len(defs.clusters)} clusters: {status}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
