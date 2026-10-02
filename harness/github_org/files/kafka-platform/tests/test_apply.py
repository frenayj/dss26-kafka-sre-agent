"""Unit tests for the planning half of scripts/apply.py - no cluster needed."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from apply import (  # noqa: E402
    Binding, desired_bindings, desired_topics, plan_acls, plan_compatibility, plan_topics,
)
from validate import load  # noqa: E402

NAME = "cards.card.issued.v1"
TOPIC = {
    "name": NAME,
    "partitions": 6,
    "replication_factor": 3,
    "config": {"cleanup.policy": "delete", "retention.ms": 1209600000},
    "value_format": "avro",
    "schema": {"subject": f"{NAME}-value", "compatibility": "BACKWARD"},
}
IN_SYNC = {"cleanup.policy": "delete", "retention.ms": "1209600000", "segment.bytes": "1073741824"}


class PlanTopicsTest(unittest.TestCase):
    def test_creates_a_missing_topic_with_its_config(self):
        (change,) = plan_topics({NAME: TOPIC}, partitions={}, configs={})
        self.assertEqual(change.kind, "create-topic")
        self.assertEqual(change.payload, (6, 3, {"cleanup.policy": "delete", "retention.ms": "1209600000"}))

    def test_nothing_to_do_when_in_sync(self):
        self.assertEqual(plan_topics({NAME: TOPIC}, {NAME: 6}, {NAME: IN_SYNC}), [])

    def test_raises_partition_count(self):
        (change,) = plan_topics({NAME: TOPIC}, {NAME: 3}, {NAME: IN_SYNC})
        self.assertEqual((change.kind, change.payload), ("add-partitions", 6))

    def test_never_lowers_partition_count(self):
        (change,) = plan_topics({NAME: TOPIC}, {NAME: 12}, {NAME: IN_SYNC})
        self.assertEqual(change.kind, "skip")

    def test_sets_only_the_drifted_configs(self):
        drifted = dict(IN_SYNC, **{"retention.ms": "86400000"})
        (change,) = plan_topics({NAME: TOPIC}, {NAME: 6}, {NAME: drifted})
        self.assertEqual((change.kind, change.payload), ("set-config", {"retention.ms": "1209600000"}))


class PlanCompatibilityTest(unittest.TestCase):
    def test_sets_a_subject_without_its_own_level(self):
        (change,) = plan_compatibility({NAME: TOPIC}, {f"{NAME}-value": None})
        self.assertEqual((change.target, change.payload), (f"{NAME}-value", "BACKWARD"))
        self.assertIn("global default -> BACKWARD", change.detail)

    def test_restores_the_declared_level(self):
        (change,) = plan_compatibility({NAME: TOPIC}, {f"{NAME}-value": "FORWARD"})
        self.assertIn("FORWARD -> BACKWARD", change.detail)

    def test_nothing_to_do_when_in_sync(self):
        self.assertEqual(plan_compatibility({NAME: TOPIC}, {f"{NAME}-value": "BACKWARD"}), [])

    def test_ignores_topics_without_a_schema(self):
        raw = dict(TOPIC, value_format="bytes", schema=None)
        self.assertEqual(plan_compatibility({NAME: raw}, {}), [])


class PlanAclsTest(unittest.TestCase):
    def test_creates_missing_and_reports_unmanaged(self):
        read = Binding("User:svc-a", "topic", NAME, "literal", "READ")
        write = Binding("User:svc-b", "topic", NAME, "literal", "WRITE")
        stray = Binding("User:svc-old", "group", "old-group", "literal", "READ")
        create, unmanaged = plan_acls({read, write}, {read, stray})
        self.assertEqual([c.payload for c in create], [write])
        self.assertEqual(unmanaged, [stray])


class RepositoryTest(unittest.TestCase):
    def test_every_cluster_has_topics_and_acls(self):
        defs = load(ROOT)
        for cluster in defs.clusters:
            with self.subTest(cluster=cluster):
                self.assertTrue(desired_topics(defs, cluster))
                bindings = desired_bindings(defs, cluster)
                self.assertTrue(bindings)
                self.assertTrue(all(b.principal.startswith("User:svc-") for b in bindings))


if __name__ == "__main__":
    unittest.main()
