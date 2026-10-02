"""Tests for the schema-compat action's script.

The parsing and reporting tests always run. The registry tests need a Schema
Registry: set SCHEMA_REGISTRY_URL (ci.yml does, with a service container).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "actions" / "schema-compat"))

import schema_compat as sc  # noqa: E402

SCHEMAS = ROOT / "tests" / "schemas"
BASE = (SCHEMAS / "clearing_matched_v1.avsc").read_text()
OPTIONAL_FIELD = (SCHEMAS / "clearing_matched_v1_optional_field.avsc").read_text()
REQUIRED_FIELD = (SCHEMAS / "clearing_matched_v1_required_field.avsc").read_text()
REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL")


class ParsePairsTest(unittest.TestCase):
    def test_one_pair_per_line(self):
        pairs = sc.parse_pairs(
            "cards.clearing.matched.v1-value=src/main/avro/clearing-matched.avsc\n"
            "cards.clearing.received.v1-value=src/main/avro/clearing-received.avsc\n"
        )
        self.assertEqual(pairs, [
            sc.Pair("cards.clearing.matched.v1-value", "src/main/avro/clearing-matched.avsc"),
            sc.Pair("cards.clearing.received.v1-value", "src/main/avro/clearing-received.avsc"),
        ])

    def test_ignores_blank_lines_comments_and_padding(self):
        pairs = sc.parse_pairs("\n  # producer schema\n  a-value = schemas/a.avsc  \n\n")
        self.assertEqual(pairs, [sc.Pair("a-value", "schemas/a.avsc")])

    def test_rejects_a_line_without_a_path(self):
        with self.assertRaisesRegex(ValueError, "line 2: expected <subject>=<path>"):
            sc.parse_pairs("a-value=a.avsc\nb-value\n")

    def test_rejects_an_empty_input(self):
        with self.assertRaisesRegex(ValueError, "no <subject>=<path> pairs"):
            sc.parse_pairs("\n# nothing here\n")


class ReportingTest(unittest.TestCase):
    PAIR = sc.Pair("cards.clearing.matched.v1-value", "src/main/avro/clearing,matched.avsc")

    def test_incompatible_schema_is_annotated_on_its_file(self):
        line = sc.annotate(sc.Result(self.PAIR, "incompatible", "READER_FIELD_MISSING_DEFAULT_VALUE\nx"))
        self.assertTrue(line.startswith("::error file=src/main/avro/clearing%2Cmatched.avsc,"))
        self.assertIn("title=cards.clearing.matched.v1-value is not BACKWARD compatible", line)
        self.assertTrue(line.endswith("::READER_FIELD_MISSING_DEFAULT_VALUE%0Ax"))

    def test_passing_results_are_not_annotated(self):
        for status in ("compatible", "new", "unchanged"):
            self.assertIsNone(sc.annotate(sc.Result(self.PAIR, status)))

    def test_branch_creation_push_is_skipped(self):
        code = sc.main(["--schemas", "a-value=a.avsc", "--base-ref", "0" * 40,
                        "--registry-url", "http://127.0.0.1:9"])
        self.assertEqual(code, 0)

    def test_summary_lists_every_schema(self):
        text = sc.summary([sc.Result(self.PAIR, "compatible"),
                           sc.Result(sc.Pair("b-value", "b.avsc"), "new", "nothing to compare")],
                          "8e3f5a9c0d7b6e2f")
        self.assertIn("base `8e3f5a9c0d7b`", text)
        self.assertIn("| `b-value` | `b.avsc` | new - nothing to compare |", text)


@unittest.skipUnless(REGISTRY_URL, "set SCHEMA_REGISTRY_URL to run against a Schema Registry")
class RegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = sc.Registry(REGISTRY_URL)
        self.registry.wait_until_ready()
        self.registry.set_level(sc.LEVEL)
        # A fresh subject per test: the registry outlives the test run.
        self.subject = f"tests.clearing.matched.{uuid.uuid4().hex[:8]}-value"
        self.registry.register(self.subject, BASE)

    def test_optional_field_with_default_is_compatible(self):
        ok, messages = self.registry.check(self.subject, OPTIONAL_FIELD)
        self.assertTrue(ok, messages)

    def test_required_field_without_default_is_not(self):
        ok, messages = self.registry.check(self.subject, REQUIRED_FIELD)
        self.assertFalse(ok)
        self.assertTrue(any("scheme_reference" in m for m in messages), messages)


@unittest.skipUnless(REGISTRY_URL, "set SCHEMA_REGISTRY_URL to run against a Schema Registry")
class EndToEndTest(unittest.TestCase):
    """A caller's checkout: base commit, then a pull request that edits the schema."""

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp(prefix="schema-compat-"))
        self.addCleanup(shutil.rmtree, self.repo)
        self.git("init", "-q", "-b", "main")
        (self.repo / "avro").mkdir()
        (self.repo / "avro" / "clearing-matched.avsc").write_text(BASE)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.subject = f"tests.e2e.{uuid.uuid4().hex[:8]}-value"

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=ci", "-c", "user.email=ci@localhost",
             "-c", "commit.gpgsign=false", *args],
            cwd=self.repo, check=True, capture_output=True, text=True,
        ).stdout

    def run_check(self, schema: str) -> int:
        (self.repo / "avro" / "clearing-matched.avsc").write_text(schema)
        return sc.main(["--schemas", f"{self.subject}=avro/clearing-matched.avsc",
                        "--base-ref", self.base, "--registry-url", REGISTRY_URL,
                        "--root", str(self.repo)])

    def test_compatible_change_passes(self):
        self.assertEqual(self.run_check(OPTIONAL_FIELD), 0)

    def test_incompatible_change_fails(self):
        self.assertEqual(self.run_check(REQUIRED_FIELD), 1)

    def test_new_schema_passes(self):
        (self.repo / "avro" / "new.avsc").write_text(BASE)
        code = sc.main(["--schemas", f"{self.subject}=avro/new.avsc", "--base-ref", self.base,
                        "--registry-url", REGISTRY_URL, "--root", str(self.repo)])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
