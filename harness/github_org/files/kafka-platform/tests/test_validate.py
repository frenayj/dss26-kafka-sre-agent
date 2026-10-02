"""Unit tests for scripts/validate.py."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate  # noqa: E402

TEAMS = """\
teams:
  - slug: cards-platform
  - slug: payments-edge
"""

CLUSTER = """\
name: cards-dev-euw1
environment: development
bootstrap_servers: localhost:9092
min_replication_factor: 3
"""

TOPIC_PATH = "topics/cards/cards.card.issued.v1.yaml"
TOPIC = """\
name: cards.card.issued.v1
owner: cards-platform
tier: tier-2
description: A new physical or virtual card has been issued.
clusters:
  - cards-dev-euw1
partitions: 3
replication_factor: 3
config:
  cleanup.policy: delete
  retention.ms: 1209600000
  min.insync.replicas: 2
value_format: avro
schema:
  subject: cards.card.issued.v1-value
  compatibility: BACKWARD
tags:
  - domain:cards
  - owner:cards-platform
  - criticality:tier-2
  - data-residency:eu
"""

ACCOUNT_PATH = "acls/svc-card-lifecycle.yaml"
ACCOUNT = """\
service_account: svc-card-lifecycle
owner: cards-platform
description: Card lifecycle service.
clusters:
  - cards-dev-euw1
acls:
  - resource: topic
    name: cards.card.issued.v1
    pattern: literal
    operations: [WRITE, DESCRIBE]
"""


class ValidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="kafka-platform-"))
        self.addCleanup(shutil.rmtree, self.root)
        self.write("teams.yaml", TEAMS)
        self.write("clusters/cards-dev-euw1.yaml", CLUSTER)
        self.write(TOPIC_PATH, TOPIC)
        self.write(ACCOUNT_PATH, ACCOUNT)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def problems(self) -> list[str]:
        return [p.message for p in validate.validate(validate.load(self.root))]

    def assertProblem(self, fragment: str) -> None:
        problems = self.problems()
        self.assertTrue(any(fragment in p for p in problems), f"{fragment!r} not in {problems}")

    def test_repository_is_valid(self):
        problems = validate.validate(validate.load(ROOT))
        self.assertEqual([p.annotation(ROOT) for p in problems], [])

    def test_minimal_definitions_are_valid(self):
        self.assertEqual(self.problems(), [])

    def test_topic_name_follows_the_convention(self):
        self.write("topics/cards/cards.CardIssued.yaml",
                   TOPIC.replace("cards.card.issued.v1", "cards.CardIssued"))
        self.assertProblem("does not follow <domain>.<entity>.<event>.v<N>")

    def test_topic_lives_in_its_domain_folder(self):
        self.write("topics/fraud/cards.card.blocked.v1.yaml", TOPIC.replace("issued", "blocked"))
        self.assertProblem("belongs in topics/cards/")

    def test_owner_is_a_known_team(self):
        self.write(TOPIC_PATH, TOPIC.replace("owner: cards-platform", "owner: card-platform"))
        self.assertProblem("owner 'card-platform' is not a team")

    def test_clusters_are_known(self):
        self.write(TOPIC_PATH, TOPIC.replace("  - cards-dev-euw1\n", "  - cards-dev-euw2\n"))
        self.assertProblem("unknown cluster 'cards-dev-euw2'")

    def test_replication_factor_meets_the_cluster_minimum(self):
        self.write(TOPIC_PATH, TOPIC.replace("replication_factor: 3", "replication_factor: 1")
                   .replace("  min.insync.replicas: 2\n", ""))
        self.assertProblem("below the minimum of 3")

    def test_min_insync_replicas_is_lower_than_replication_factor(self):
        self.write(TOPIC_PATH, TOPIC.replace("min.insync.replicas: 2", "min.insync.replicas: 3"))
        self.assertProblem("min.insync.replicas must be lower")

    def test_avro_topic_declares_its_subject(self):
        self.write(TOPIC_PATH, TOPIC.replace("subject: cards.card.issued.v1-value",
                                             "subject: cards-card-issued"))
        self.assertProblem("schema.subject must be cards.card.issued.v1-value")

    def test_cards_subjects_stay_backward_compatible(self):
        self.write(TOPIC_PATH, TOPIC.replace("compatibility: BACKWARD", "compatibility: NONE"))
        self.assertProblem("cards subjects must be BACKWARD compatible or stricter")

    def test_tags_agree_with_owner_and_tier(self):
        self.write(TOPIC_PATH, TOPIC.replace("criticality:tier-2", "criticality:tier-1"))
        self.assertProblem("missing tag criticality:tier-2")

    def test_dead_letter_topic_names_its_source(self):
        dlq = TOPIC.replace("name: cards.card.issued.v1", "name: cards.card.issued.v1.dlq").replace(
            "value_format: avro\nschema:\n  subject: cards.card.issued.v1-value\n"
            "  compatibility: BACKWARD\n",
            "value_format: bytes\ndead_letter_for: cards.card.issued.v1\n",
        )
        self.write("topics/cards/cards.card.issued.v1.dlq.yaml", dlq)
        self.assertEqual(self.problems(), [])
        self.write("topics/cards/cards.card.issued.v1.dlq.yaml",
                   dlq.replace("dead_letter_for: cards.card.issued.v1", "dead_letter_for: cards.card.v1"))
        self.assertProblem("dead_letter_for must be cards.card.issued.v1")

    def test_acl_topic_is_declared(self):
        self.write(ACCOUNT_PATH, ACCOUNT.replace("name: cards.card.issued.v1", "name: cards.card.isued.v1"))
        self.assertProblem("topic cards.card.isued.v1 is not declared")

    def test_prefixed_write_does_not_cover_catalogue_topics(self):
        self.write(ACCOUNT_PATH, ACCOUNT.replace("name: cards.card.issued.v1\n    pattern: literal",
                                                 "name: cards.card.\n    pattern: prefixed"))
        self.assertProblem("prefixed write access on 'cards.card.'")

    def test_wildcard_grants_are_read_only(self):
        wildcard = ACCOUNT.replace("svc-card-lifecycle", "svc-oncall-tools").replace(
            "name: cards.card.issued.v1", 'name: "*"')
        self.write("acls/svc-oncall-tools.yaml", wildcard.replace("[WRITE, DESCRIBE]", "[READ, DESCRIBE]"))
        self.assertEqual(self.problems(), [])
        self.write("acls/svc-oncall-tools.yaml", wildcard)
        self.assertProblem("wildcard grants are read-only")

    def test_account_file_is_named_after_the_account(self):
        self.write("acls/svc-cards.yaml", ACCOUNT)
        self.assertProblem("file name must be svc-card-lifecycle.yaml")


if __name__ == "__main__":
    unittest.main()
