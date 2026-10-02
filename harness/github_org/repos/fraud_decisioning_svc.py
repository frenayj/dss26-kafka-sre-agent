"""dss26-org/fraud-decisioning-svc - the Tier-1 consumer that gets paged.

Story role (schema break): the victim, not the cause. It reads
``cards.authorisation.requested.v1`` with the v1 reader schema pinned and fails
closed on a record it cannot read, exactly like ``harness/stack/fraud_scoring/
fraud_scorer.py``. When merchant-gateway's culprit registers a v2 with a string
``amount``, this service stops on that record, lag grows and ledger postings
stop.

* History 2021-11 -> 2026-09: fraud-scoring (JSON, then Avro per ADR-0007,
  fail closed from 2022-04), the ADR-0011 rename in May/June 2024, the
  schema-compat CI job from October 2024, the INC-2025-03-18-002 GC /
  max.poll.interval.ms fix, Datadog monitors as code in 2026.
* Decoys merged the morning of the incident: jordan.k lowering
  session.timeout.ms (a plausible lag suspect next to the 2025 rebalance
  incident, harmless here) and a confluent-kafka patch bump.
* Open PR: alex.chen's consumer-side change for CARDS-1502 (decimal-string
  amount), the change the 2026-04-29 ops review said must ship first. It is
  still waiting on a load test.

The two .avsc files under ``schemas/`` are read from ``harness/stack/schemas`` at
import time so the repo and the running cluster cannot drift.
"""

from __future__ import annotations

import json

from model import (
    DEFAULT_LABELS,
    FILES_ROOT,
    REPO_ROOT,
    Commit,
    Delete,
    Edit,
    Label,
    RepoSpec,
    ScenarioPR,
    Write,
)

REPO = "fraud-decisioning-svc"
F = "fraud-decisioning-svc"  # files/ subfolder
FILES = FILES_ROOT / F
HIST = FILES / "_history"

AUTH_AVSC = "schemas/cards_authorisation_requested_v1.avsc"
LEDGER_AVSC = "schemas/cards_ledger_posted_v1.avsc"
SCHEMA_SRC = REPO_ROOT / "harness" / "stack" / "schemas"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(rel: str) -> str:
    return (FILES / rel).read_text()


def _sub(text: str, *pairs: tuple[str, str], where: str = "") -> str:
    """Apply exact single-occurrence replacements (fails loudly on drift)."""
    for old, new in pairs:
        n = text.count(old)
        if n != 1:
            raise ValueError(f"{REPO} {where}: expected 1 match of {old[:70]!r}, found {n}")
        text = text.replace(old, new)
    return text


def _drop_defs(text: str, *names: str) -> str:
    """Remove top-level blocks (separated by two blank lines) defining ``names``."""
    chunks = text.split("\n\n\n")
    kept = [c for c in chunks if not any(f"def {n}(" in c for n in names)]
    if len(chunks) - len(kept) != len(names):
        raise ValueError(f"{REPO}: could not drop all of {names}")
    out = "\n\n\n".join(kept)
    return out if out.endswith("\n") else out + "\n"


def _scoring_era(text: str) -> str:
    """The same file before ADR-0011: package fraud_scoring, group fraud-scoring-consumer."""
    for old, new in (
        ("fraud-decisioning-engine", "fraud-scoring-consumer"),
        ("fraud_decisioning", "fraud_scoring"),
        ("fraud-decisioning-svc", "fraud-scoring"),
        ("fraud-decisioning", "fraud-scoring"),
    ):
        text = text.replace(old, new)
    return text


def _old_group(text: str) -> str:
    """Renamed package, consumer group not switched yet (2024-06-04..06-11)."""
    return text.replace("fraud-decisioning-engine", "fraud-scoring-consumer")


def _avsc(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _pkg(era_fn, files: dict[str, str], pkg: str) -> tuple[Write, ...]:
    return tuple(Write(f"{pkg}/{name}", era_fn(text)) for name, text in files.items())


# ---------------------------------------------------------------------------
# Schemas (byte-identical to harness/stack/schemas at the seeded head)
# ---------------------------------------------------------------------------

AUTH_FINAL = (SCHEMA_SRC / "cards_authorisation_requested_v1.avsc").read_text()
LEDGER_FINAL = (SCHEMA_SRC / "cards_ledger_posted_v1.avsc").read_text()
assert _avsc(json.loads(AUTH_FINAL)) == AUTH_FINAL, "auth schema is not json.dumps(indent=2) formatted"
assert _avsc(json.loads(LEDGER_FINAL)) == LEDGER_FINAL, "ledger schema is not json.dumps(indent=2) formatted"


def _auth_2022() -> str:
    """Reader copy before merchant-gateway added ``tier`` (synced 2023-05)."""
    obj = json.loads(AUTH_FINAL)
    obj["fields"] = [f for f in obj["fields"] if f["name"] != "tier"]
    return _avsc(obj)


def _ledger(decision: bool, renamed: bool) -> str:
    obj = json.loads(LEDGER_FINAL)
    if not decision:
        obj["fields"] = [f for f in obj["fields"] if f["name"] != "decision"]
    if not renamed:
        obj["doc"] = obj["doc"].replace("fraud-decisioning engine", "fraud-scoring service")
        for f in obj["fields"]:
            if f["name"] == "risk_score":
                f["doc"] = f["doc"].replace("Fraud-decisioning engine score", "Fraud-scoring score")
    out = _avsc(obj)
    if decision and renamed:
        assert out == LEDGER_FINAL
    return out


def _v2_proposed() -> str:
    """merchant-gateway's draft v2 (CARDS-1502), as attached to the ticket."""
    obj = json.loads((SCHEMA_SRC / "cards_authorisation_requested_v1_breaking.avsc").read_text())
    obj.pop("_comment_break", None)
    return _avsc(obj)


# ---------------------------------------------------------------------------
# Package sources: final versions from files/, older ones derived from them
# ---------------------------------------------------------------------------

F_CONFIG = _read("fraud_decisioning/config.py")
F_CONSUMER = _read("fraud_decisioning/consumer.py")
F_LEDGER = _read("fraud_decisioning/ledger.py")
F_MAIN = _read("fraud_decisioning/__main__.py")
F_METRICS = _read("fraud_decisioning/metrics.py")
F_RUNTIME = _read("fraud_decisioning/runtime.py")
F_SCHEMAS = _read("fraud_decisioning/schemas.py")
F_SCORING = _read("fraud_decisioning/scoring.py")
F_SERDE = _read("fraud_decisioning/serde.py")

T_CONFIG = _read("tests/test_config.py")
T_CONSUMER = _read("tests/test_consumer.py")
T_DEPLOY = _read("tests/test_deploy_values.py")
T_LEDGER = _read("tests/test_ledger.py")
T_SCORING = _read("tests/test_scoring.py")


def _init(version: str, scoring: bool = False) -> str:
    if scoring:
        return f'"""fraud-scoring: real-time risk scores for card authorisations."""\n\n__version__ = "{version}"\n'
    return (
        '"""fraud-decisioning-svc: approve, review or decline card authorisations."""\n\n'
        f'__version__ = "{version}"\n'
    )


assert _init("2.6.0") == _read("fraud_decisioning/__init__.py")

# --- scoring.py: signals (2021) -> amount bands (2022-12) -> cross-border
# (2023-07) -> de-duplicated signals (2025-09) -> VELOCITY_HIGH 0.45 (2026-02)
SCORING_4 = _sub(F_SCORING, ('"VELOCITY_HIGH": 0.45,', '"VELOCITY_HIGH": 0.40,'), where="scoring 4")
SCORING_3 = _sub(SCORING_4, (
    "    if not raw:\n        return ()\n"
    "    # De-duplicate: the gateway occasionally repeats a code when two of its\n"
    "    # checks raise the same signal.\n"
    "    return dict.fromkeys(str(s).upper() for s in raw)\n",
    "    if not raw:\n        return ()\n"
    "    return [str(s).upper() for s in raw]\n",
), where="scoring 3")
SCORING_2 = _sub(
    SCORING_3,
    ("channel base rate, an amount band, a cross-border weight and one weight per\n"
     "risk signal the merchant gateway attached, capped at 1.0.",
     "channel base rate, an amount band and one weight per risk signal the\n"
     "merchant gateway attached, capped at 1.0."),
    ("\nCROSS_BORDER_WEIGHT = 0.10\n"
     "# Merchant countries treated as domestic: the EEA, plus GB and CH (RISK-207).\n"
     "DOMESTIC_COUNTRIES = frozenset(\n"
     '    "AT BE BG CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT LU LV MT NL NO "\n'
     '    "PL PT RO SE SI SK".split()\n'
     ")\n", ""),
    ('    country = auth.get("country")\n'
     "    if country and country not in DOMESTIC_COUNTRIES:\n"
     "        score += CROSS_BORDER_WEIGHT\n"
     '        reasons.append("CROSS_BORDER")\n\n', ""),
    where="scoring 2",
)
SCORING_1 = _sub(
    SCORING_2,
    ("channel base rate, an amount band and one weight per risk signal the\n"
     "merchant gateway attached, capped at 1.0.",
     "channel base rate and one weight per risk signal the merchant gateway\n"
     "attached, capped at 1.0."),
    ("\n# (lower bound in major units, weight), highest band first.\n"
     "AMOUNT_BANDS = ((5000.0, 0.25), (1000.0, 0.10))\n", ""),
    ('    amount = float(auth["amount"])\n'
     "    for floor, weight in AMOUNT_BANDS:\n"
     "        if amount >= floor:\n"
     "            score += weight\n"
     '            reasons.append(f"AMOUNT_GE_{int(floor)}")\n'
     "            break\n\n", ""),
    where="scoring 1",
)

T_SCORING_3 = _drop_defs(T_SCORING, "test_repeated_signal_counts_once")
T_SCORING_2 = _drop_defs(T_SCORING_3, "test_cross_border_merchant")
T_SCORING_1 = _drop_defs(
    T_SCORING_2,
    "test_high_velocity_new_device_high_value_is_declined",
    "test_only_the_highest_amount_band_counts",
)

# --- ledger.py: extracted 2023-03 (uuid4) -> uuid5 posting ids (2023-09)
# -> decision field (2024-05, ADR-0011)
LEDGER_2 = _sub(F_LEDGER, ('        "decision": assessment.outcome,\n', ""), where="ledger 2")
LEDGER_1 = _sub(
    LEDGER_2,
    ("# Fixed namespace for posting ids. Never change it: the General Ledger\n"
     "# de-duplicates on posting_id, and a new namespace would make every replayed\n"
     "# authorisation look like a new posting.\n"
     'POSTING_NAMESPACE = uuid.UUID("5b0e7c2a-91d4-4f3e-8a66-2c7d0f9e4b18")\n\n\n'
     "def posting_id_for(auth_id: str) -> str:\n"
     '    """Same authorisation, same posting id - a replay cannot double-post."""\n'
     "    return str(uuid.uuid5(POSTING_NAMESPACE, auth_id))\n\n", ""),
    ('"posting_id": posting_id_for(auth["auth_id"]),', '"posting_id": str(uuid.uuid4()),'),
    where="ledger 1",
)

_LEDGER_HEADER = T_LEDGER[: T_LEDGER.index("AUTH = {")]
T_LEDGER_1 = _drop_defs(
    _sub(
        T_LEDGER,
        (_LEDGER_HEADER,
         "from fraud_decisioning.ledger import posting_id_for, to_posting\n"
         "from fraud_decisioning.scoring import assess\n\n"),
        ('        "decision": assessment.outcome,\n', ""),
        where="test_ledger 1",
    ),
    "test_posting_matches_the_ledger_schema",
    "test_round_trip_through_the_pinned_reader_schema",
)

# --- consumer.py (batch loop from 2023-03)
CONSUMER_2023 = _sub(
    F_CONSUMER,
    ("    Nothing from the batch was committed. The process exits and restarts from\n"
     "    the last committed offsets; postings are idempotent by posting_id.\n",
     "    Nothing from the batch was committed. The process exits and restarts from\n"
     "    the last committed offsets.\n"),
    ("            # Typically a rebalance in flight. The new owner re-reads from the\n"
     "            # last committed offset; the postings it repeats carry the same\n"
     "            # posting_id and are de-duplicated by the General Ledger.\n",
     "            # Typically a rebalance in flight. The new owner re-reads from the\n"
     "            # last committed offset.\n"),
    where="consumer 2023",
)
# 2025-02-25: automatic GC off, full collection between batches. Reverted by
# the INC-2025-03-18-002 fix.
CONSUMER_GC = _sub(
    F_CONSUMER,
    ("from fraud_decisioning import metrics\n", "from fraud_decisioning import metrics, runtime\n"),
    ("        metrics.BATCH_SECONDS.observe(self._clock() - started)\n        return posted\n",
     "        metrics.BATCH_SECONDS.observe(self._clock() - started)\n"
     "        runtime.collect_between_batches()\n        return posted\n"),
    where="consumer gc",
)
RUNTIME_GC = '''"""Process-level tuning for the decisioning loop.

Automatic garbage collection is switched off and the loop collects between
batches instead, so a gen-2 collection never lands in the middle of a batch and
holds up every decision in it (p99 decision latency, CARDS-1251).
"""

from __future__ import annotations

import gc

# Collect once this many allocations have piled up since the last collection.
COLLECT_AFTER = 200_000


def tune_gc() -> None:
    """Call once, after startup allocations and before the loop starts."""
    gc.disable()


def collect_between_batches() -> None:
    if gc.get_count()[0] >= COLLECT_AFTER:
        gc.collect()
'''

T_CONSUMER_2023 = _sub(
    T_CONSUMER,
    ("from fraud_decisioning.ledger import posting_id_for\n", ""),
    ('    assert producer.produced[0][2]["posting_id"] == posting_id_for("a")\n', ""),
    where="test_consumer 2023",
)

# --- config.py
CONFIG_PRE_INC = _sub(
    F_CONFIG,
    ("# INC-2025-03-18-002: batches of 2000 plus a full GC could take longer than\n"
     "# max.poll.interval.ms. 500 keeps a batch well under a second at peak.\n"
     "DEFAULT_BATCH_SIZE = 500\n", "DEFAULT_BATCH_SIZE = 2000\n"),
    where="config pre-INC",
)
CONFIG_2022 = (HIST / "config_2022.py").read_text()
CONFIG_2021_METRICS = _sub(
    CONFIG_2022,
    ("from dataclasses import dataclass\nfrom pathlib import Path\n\n"
     'SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"\n',
     "from dataclasses import dataclass\n"),
    ("    schema_registry_url: str\n", ""),
    ('    reader_schema_path: Path = SCHEMA_DIR / "cards_authorisation_requested_v1.avsc"\n'
     '    ledger_schema_path: Path = SCHEMA_DIR / "cards_ledger_posted_v1.avsc"\n', ""),
    ('        schema_registry_url=os.environ["SCHEMA_REGISTRY_URL"],\n', ""),
    where="config 2021+metrics",
)
CONFIG_2021 = _sub(
    CONFIG_2021_METRICS,
    ("    metrics_port: int = 9102\n", ""),
    ('        metrics_port=int(os.environ.get("METRICS_PORT", "9102")),\n', ""),
    where="config 2021",
)

# --- metrics.py: decisions/postings (2022-01) -> + deserialisation errors
# (2022-04, fail closed) -> full set with the batch loop (2023-03)
METRICS_2 = _sub(
    F_METRICS,
    ("from prometheus_client import Counter, Gauge, Histogram, start_http_server\n",
     "from prometheus_client import Counter, start_http_server\n"),
    ("POSTING_ERRORS = Counter(\n"
     '    "fraud_decisioning_ledger_posting_errors",\n'
     '    "Ledger postings rejected or not acknowledged in time.",\n'
     ")\n"
     "BATCH_SECONDS = Histogram(\n"
     '    "fraud_decisioning_batch_seconds",\n'
     '    "Time to decide, post and commit one batch.",\n'
     "    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),\n"
     ")\n", ""),
    ("BLOCKED_PARTITIONS = Gauge(\n"
     '    "fraud_decisioning_blocked_partitions",\n'
     '    "Partitions held at a record that cannot be read.",\n'
     ")\n", ""),
    where="metrics 2",
)
METRICS_1 = _sub(
    METRICS_2,
    ("DESERIALISATION_ERRORS = Counter(\n"
     '    "fraud_decisioning_deserialisation_errors",\n'
     '    "Records the pinned reader schema could not read, by partition.",\n'
     '    ["partition"],\n'
     ")\n", ""),
    where="metrics 1",
)

# --- __main__.py
MAIN_2022 = (HIST / "main_2022.py").read_text()
MAIN_2021 = _sub(
    MAIN_2022,
    ("from fraud_scoring import config, metrics\n", "from fraud_scoring import config\n"),
    ("    metrics.serve(settings.metrics_port)\n", ""),
    where="main 2021",
)
MAIN_NO_RUNTIME = _sub(
    F_MAIN,
    ("from fraud_decisioning import __version__, config, metrics, runtime, schemas\n",
     "from fraud_decisioning import __version__, config, metrics, schemas\n"),
    ("    runtime.tune_gc()\n", ""),
    where="main pre-gc",
)

# --- legacy single-file consumers
CONSUMER_2021 = (HIST / "consumer_2021.py").read_text()
CONSUMER_2022 = (HIST / "consumer_2022.py").read_text()
# 2022-03-22, Avro but still skipping unreadable records (fail closed came two
# weeks later).
CONSUMER_2022_SKIP = _sub(
    CONSUMER_2022,
    ('\nRecords are Avro (ADR-0007), read with the reader schema pinned in schemas/.\n'
     'We never commit past a record we cannot read: see README, "Fail closed".\n',
     "\nRecords are Avro (ADR-0007), read with the reader schema pinned in schemas/.\n"),
    ("from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition\n",
     "from confluent_kafka import Consumer, KafkaError, Producer\n"),
    ("    # (topic, partition, offset) of a record we could not read. We seek back\n"
     "    # to it until it can be read; nothing after it is committed.\n"
     "    held = None\n\n", ""),
    ("            if held is not None:\n"
     "                consumer.seek(TopicPartition(*held))\n"
     "                time.sleep(1)\n\n", ""),
    ("            where = (msg.topic(), msg.partition(), msg.offset())\n"
     "            ctx = SerializationContext(msg.topic(), MessageField.VALUE)\n"
     "            try:\n"
     "                auth = deserialise(msg.value(), ctx)\n"
     "            except Exception as exc:\n"
     "                metrics.DESERIALISATION_ERRORS.labels(str(msg.partition())).inc()\n"
     "                if held != where:\n"
     "                    log.error(\n"
     '                        "cannot read %s[%d]@%d: %s: %s - holding here, not committing past it",\n'
     "                        *where, type(exc).__name__, exc,\n"
     "                    )\n"
     "                held = where\n"
     "                continue\n"
     "            if held == where:\n"
     '                log.info("%s[%d]@%d readable again", *where)\n'
     "                held = None\n",
     "            ctx = SerializationContext(msg.topic(), MessageField.VALUE)\n"
     "            try:\n"
     "                auth = deserialise(msg.value(), ctx)\n"
     "            except Exception as exc:\n"
     "                log.warning(\n"
     '                    "skipping unreadable record at %s[%d]@%d: %s",\n'
     "                    msg.topic(), msg.partition(), msg.offset(), exc,\n"
     "                )\n"
     "                consumer.commit(message=msg, asynchronous=False)\n"
     "                continue\n"),
    where="consumer 2022 skip",
)


# ---------------------------------------------------------------------------
# Small repo files, rendered per era
# ---------------------------------------------------------------------------


def requirements(ck: str, fa: str | None = None, prom: str | None = None,
                 header: bool = True, hold: bool = False) -> str:
    lines = []
    if header:
        lines.append("# Runtime dependencies, pinned. Updated by dss26-platform-bot.")
    if hold:
        lines += [
            "# confluent-kafka: patch releases only - librdkafka minors are soaked in uat",
            "# by the Kafka platform team first (PLAT-622).",
        ]
    lines.append(f"confluent-kafka[avro]=={ck}" if fa else f"confluent-kafka=={ck}")
    if fa:
        lines.append(f"fastavro=={fa}")
    if prom:
        lines.append(f"prometheus-client=={prom}")
    return "\n".join(lines) + "\n"


def requirements_dev(pytest: str, ruff: str | None = None, pyyaml: bool = False) -> str:
    lines = ["-r requirements.txt", f"pytest=={pytest}"]
    if pyyaml:
        lines.append("pyyaml==6.0.2")
    if ruff:
        lines.append(f"ruff=={ruff}")
    return "\n".join(lines) + "\n"


def pyproject(stage: str) -> str:
    if stage == "2021":
        return '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    name, desc = ("fraud-scoring", "Real-time risk scores for card authorisations.")
    if stage not in ("2023",):
        name, desc = ("fraud-decisioning-svc",
                      "Approves, reviews or declines card authorisations and posts them to the ledger.")
    py = "3.12" if stage == "final" else "3.11"
    deps = (('"confluent-kafka[avro]>=2.5,<2.6"', '"fastavro>=1.9"', '"prometheus-client>=0.19"')
            if stage in ("2025-01", "final") else
            ('"confluent-kafka[avro]>=2.0"', '"fastavro>=1.7"', '"prometheus-client>=0.16"'))
    ruff = ('[tool.ruff]\nline-length = 100\ntarget-version = "py312"\n\n'
            '[tool.ruff.lint]\nselect = ["E", "F", "I", "B", "UP"]\n') if stage == "final" else (
            '[tool.ruff]\nline-length = 100\ntarget-version = "py311"\n'
            'select = ["E", "F", "I", "B", "UP"]\n')
    return (
        "[project]\n"
        f'name = "{name}"\n'
        f'description = "{desc}"\n'
        f'requires-python = ">={py}"\n'
        'dynamic = ["version"]\n'
        "dependencies = [\n" + "".join(f"    {d},\n" for d in deps) + "]\n\n"
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n'
        'pythonpath = ["."]\n'
        'addopts = "-ra"\n\n' + ruff
    )


def dockerfile(py: str, pkg: str, schemas: bool = True, user: bool = True) -> str:
    out = (
        f"FROM python:{py}-slim\n\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 \\\n    PYTHONUNBUFFERED=1\n\n"
        "WORKDIR /app\n\n"
        "COPY requirements.txt ./\n"
        "RUN pip install --no-cache-dir -r requirements.txt\n\n"
        f"COPY {pkg}/ {pkg}/\n"
    )
    if schemas:
        out += "COPY schemas/ schemas/\n"
    if user:
        out += "\nRUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app\nUSER 10001\n"
    out += f'\nEXPOSE 9102\nENTRYPOINT ["python", "-m", "{pkg}"]\n'
    return out


def ci(py: str = "3.12", checkout: str = "v4", setup_python: str = "v5", lint: bool = True,
       compat: bool = True, image: str | None = "fraud-decisioning-svc",
       login: str = "v3", build_push: str = "v6") -> str:
    if lint:
        steps = (
            f"      - uses: actions/checkout@{checkout}\n"
            f"      - uses: actions/setup-python@{setup_python}\n"
            "        with:\n"
            f'          python-version: "{py}"\n'
            "          cache: pip\n"
            "          cache-dependency-path: requirements-dev.txt\n"
            "      - name: Install\n"
            "        run: pip install -r requirements-dev.txt\n"
            "      - name: Lint\n"
            "        run: ruff check .\n"
            "      - name: Unit tests\n"
            "        run: pytest\n"
        )
    else:
        steps = (
            f"      - uses: actions/checkout@{checkout}\n"
            f"      - uses: actions/setup-python@{setup_python}\n"
            "        with:\n"
            f'          python-version: "{py}"\n'
            "      - name: Install\n"
            "        run: pip install -r requirements-dev.txt\n"
            "      - name: Unit tests\n"
            "        run: python -m pytest\n"
        )
    out = (
        "name: ci\n\n"
        "on:\n  pull_request:\n  push:\n    branches: [main]\n\n"
        "permissions:\n  contents: read\n\n"
        "jobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n" + steps
    )
    if compat:
        out += (
            "\n  # INC-2024-09-12-003: every cards repo checks the schemas it produces\n"
            "  # against the registry before merge.\n"
            "  schema-compat:\n"
            "    uses: dss26-org/cards-ci-workflows/.github/workflows/schema-compat.yml@main\n"
            "    with:\n"
            "      schemas: |\n"
            "        cards.ledger.posted.v1-value=schemas/cards_ledger_posted_v1.avsc\n"
        )
    if image:
        out += (
            "\n  image:\n"
            "    needs: test\n"
            "    # Harbor is only reachable from the bank's runners; elsewhere, skip the push.\n"
            "    if: github.event_name == 'push' && vars.HARBOR_REGISTRY != ''\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            f"      - uses: actions/checkout@{checkout}\n"
            f"      - uses: docker/login-action@{login}\n"
            "        with:\n"
            "          registry: harbor.dss26.internal\n"
            "          username: ${{ secrets.HARBOR_USERNAME }}\n"
            "          password: ${{ secrets.HARBOR_PASSWORD }}\n"
            f"      - uses: docker/build-push-action@{build_push}\n"
            "        with:\n"
            "          context: .\n"
            "          push: true\n"
            f"          tags: harbor.dss26.internal/cards-platform/{image}:${{{{ github.sha }}}}\n"
        )
    return out


assert ci() == _read(".github/workflows/ci.yml"), "ci() drifted from files/"
assert pyproject("final") == _read("pyproject.toml"), "pyproject() drifted from files/"
assert dockerfile("3.12", "fraud_decisioning") == _read("Dockerfile"), "dockerfile() drifted from files/"


def catalog(stage: str) -> str:
    """catalog-info.yaml. Stages: 2021, 2022-11, 2024-06-04, 2024-06-11, 2025-06."""
    renamed = stage in ("2024-06-04", "2024-06-11", "2025-06")
    name = "fraud-decisioning-svc" if renamed else "fraud-scoring"
    title = "Fraud decisioning service" if renamed else "Fraud scoring service"
    desc = ("Tier-1 service that approves, reviews or declines card authorisations "
            "and posts them to the ledger."
            if renamed else "Real-time risk scores for card authorisations, posted to the ledger.")
    group = "fraud-decisioning-engine" if stage in ("2024-06-11", "2025-06") else "fraud-scoring-consumer"
    cluster = "kafka-dc1" if stage == "2021" else "cards-prod-euw1"
    paging = ("    pagerduty.com/service-id: PSVC42A\n    datadoghq.com/site: datadoghq.eu\n"
              if stage == "2025-06" else "    opsgenie.com/team: cards-platform\n")
    links = [
        (f"https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3979968513/Service+{name}", "Service page (Confluence)"),
    ]
    if renamed:
        links.append(("https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3979247620/ADR-0011+Rename+fraud-scoring+to+fraud-decisioning",
                      "ADR-0011 - Rename fraud-scoring to fraud-decisioning"))
    if stage == "2025-06":
        links += [
            ("https://dss26.pagerduty.com/service-directory/PSVC42A", "PagerDuty - fraud-decisioning-svc"),
            ("https://app.datadoghq.eu/dashboard/k3p-9xv-2mw/fraud-decisioning-svc", "Datadog dashboard"),
        ]
    return (
        "apiVersion: backstage.io/v1alpha1\n"
        "kind: Component\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  title: {title}\n"
        f"  description: {desc}\n"
        "  annotations:\n"
        f"    github.com/project-slug: dss26-org/{REPO}\n"
        "    backstage.io/techdocs-ref: dir:.\n"
        f"{paging}"
        f"    dss26.bank/consumer-group: {group}\n"
        f"    dss26.bank/kafka-cluster: {cluster}\n"
        "    dss26.bank/kafka-consumes: cards.authorisation.requested.v1\n"
        "    dss26.bank/kafka-produces: cards.ledger.posted.v1\n"
        "  tags: [kafka, python, tier-1, sox, pci-dss]\n"
        "  links:\n"
        + "".join(f"    - url: {u}\n      title: {t}\n" for u, t in links)
        + "spec:\n"
        "  type: service\n"
        "  lifecycle: production\n"
        "  owner: group:cards-platform\n"
        "  system: cards-authorisation\n"
        "  consumesApis:\n"
        "    - cards-authorisation-requested-v1\n"
        "  providesApis:\n"
        "    - cards-ledger-posted-v1\n"
    )


CODEOWNERS = """\
# Tier-1 card flow: every change needs a Cards Platform review.
*            @dss26-org/cards-platform
/.github/    @dss26-org/cards-platform @dss26-org/platform-engineering
"""

PR_TEMPLATE = """\
## What

## Why

## Risk and rollout
<!-- Tier-1 flow: production changes need a CHG ticket. For consumer-config
     and schema changes, say how you tested them (uat, load test). -->
- CHG:

## Schema impact
- [ ] none
- [ ] reader schema (`schemas/cards_authorisation_requested_v1.avsc`)
- [ ] ledger schema (`schemas/cards_ledger_posted_v1.avsc`) - schema-compat must pass
"""

ATLANTIS = """\
version: 3
projects:
  - name: fraud-decisioning-monitoring
    dir: monitoring
    terraform_version: v1.9.8
    autoplan:
      when_modified: ["*.tf"]
    apply_requirements: [approved, mergeable]
"""


def gitignore(ruff: bool = True, terraform: bool = True) -> str:
    out = "__pycache__/\n*.pyc\n.venv/\n.pytest_cache/\n"
    if ruff:
        out += ".ruff_cache/\n"
    if terraform:
        out += ".terraform/\n"
    return out


def dockerignore(monitoring: bool = True) -> str:
    out = ".git\n.github\n.venv\ntests\ndeploy\n"
    if monitoring:
        out += "monitoring\n"
    return out + "**/__pycache__\n"


# --- deploy/helm values: final from files/, earlier stages walk backwards
VALUES_FINAL = {env: _read(f"deploy/helm/values-{env}.yaml") for env in ("prod", "uat")}
VALUES_STAGES = ("2023-03", "2023-06", "2024-02", "2024-06-04", "2024-06-11",
                 "2025-01", "2025-03", "2025-08")


def values(env: str, stage: str) -> str:
    text = VALUES_FINAL[env]
    order = VALUES_STAGES[::-1]
    for st in order:
        if st == stage:
            return text
        w = f"values-{env} before {st}"
        if st == "2025-08":
            if env == "prod":
                text = _sub(text, ("    memory: 1536Mi\n", "    memory: 1Gi\n"), where=w)
        elif st == "2025-03":
            text = _sub(
                text,
                ("    # INC-2025-03-18-002: 30000 was too tight for a full GC plus a batch and\n"
                 "    # the group rebalanced every few minutes. Do not lower without a load test.\n"
                 "    max.poll.interval.ms: 300000\n", "    max.poll.interval.ms: 30000\n"),
                ('  BATCH_SIZE: "500"\n', '  BATCH_SIZE: "2000"\n'),
                where=w,
            )
        elif st == "2025-01":
            text = _sub(text, (
                "  ad.datadoghq.com/fraud-decisioning-svc.checks: |\n"
                '    {"openmetrics": {"instances": [{"openmetrics_endpoint": "http://%%host%%:9102/metrics",\n'
                '      "namespace": "fraud_decisioning", "metrics": ["fraud_decisioning_.*"]}]}}\n',
                '  prometheus.io/scrape: "true"\n  prometheus.io/port: "9102"\n'), where=w)
        elif st == "2024-06-11":
            text = _old_group(text)
        elif st == "2024-06-04":
            text = _scoring_era(text)
        elif st == "2024-02":
            text = _sub(text, ("    max.poll.interval.ms: 30000\n",
                               "    max.poll.interval.ms: 300000\n"), where=w)
        elif st == "2023-06":
            text = _sub(text, ("    session.timeout.ms: 45000\n",
                               "    session.timeout.ms: 10000\n"), where=w)
    raise KeyError(stage)


VALUES_2021 = (HIST / "values-prod_2021.yaml").read_text()

README_2021 = (HIST / "README_2021.md").read_text()
README_2024 = (HIST / "README_2024.md").read_text()

FAIL_CLOSED_2022 = """\
## Fail closed

A record that cannot be read with the pinned reader schema is never skipped.
We seek back to it and retry once a second; nothing after it is committed.

Approving or declining without a readable amount is not an option: approving
lets an unscored payment through, declining fails a customer's card for no
reason of theirs, and skipping leaves an authorisation without a score and a
hole in the ledger. The lag alert pages a human instead.

## Running
"""


# ---------------------------------------------------------------------------
# Package file sets per era
# ---------------------------------------------------------------------------

PKG_BATCH_2023 = {
    "config.py": CONFIG_PRE_INC,
    "consumer.py": CONSUMER_2023,
    "ledger.py": LEDGER_1,
    "metrics.py": F_METRICS,
    "schemas.py": F_SCHEMAS,
    "serde.py": F_SERDE,
    "__main__.py": MAIN_NO_RUNTIME,
}

PKG_RENAMED = {
    "__init__.py": _init("2.0.0"),
    "__main__.py": MAIN_NO_RUNTIME,
    "config.py": CONFIG_PRE_INC,
    "consumer.py": F_CONSUMER,
    "ledger.py": F_LEDGER,
    "metrics.py": F_METRICS,
    "schemas.py": F_SCHEMAS,
    "scoring.py": SCORING_3,
    "serde.py": F_SERDE,
}

OLD_PKG_FILES = ("__init__.py", "__main__.py", "config.py", "consumer.py", "ledger.py",
                 "metrics.py", "schemas.py", "scoring.py", "serde.py")


def _values_both(stage: str) -> tuple[Write, ...]:
    return tuple(Write(f"deploy/helm/values-{env}.yaml", values(env, stage)) for env in ("prod", "uat"))


SP = "fraud_scoring"
DP = "fraud_decisioning"

HISTORY: tuple[Commit, ...] = (
    Commit("2021-11-22 10:14", "alex.chen",
           "feat: fraud-scoring consumer for cards.authorisation.requested.v1\n\n"
           "Streams authorisation requests through the same signal rules the\n"
           "nightly batch job used, so a risk score is available seconds after the\n"
           "authorisation instead of the next morning. Consumes as\n"
           "fraud-scoring-consumer and posts one record per authorisation to\n"
           "cards.ledger.posted.v1 (JSON for now).\n\n"
           "Refs: CARDS-1003",
           (
               Write("README.md", README_2021),
               Write("catalog-info.yaml", catalog("2021")),
               Write(".github/CODEOWNERS", CODEOWNERS),
               Write(".gitignore", gitignore(ruff=False, terraform=False)),
               Write("requirements.txt", requirements("1.7.0", header=False)),
               Write("requirements-dev.txt", requirements_dev("6.2.5")),
               Write("pyproject.toml", pyproject("2021")),
               Write("Dockerfile", dockerfile("3.9", SP, schemas=False, user=False)),
               Write(f"{SP}/__init__.py", _init("0.1.0", scoring=True)),
               Write(f"{SP}/__main__.py", MAIN_2021),
               Write(f"{SP}/config.py", CONFIG_2021),
               Write(f"{SP}/consumer.py", CONSUMER_2021),
               Write(f"{SP}/scoring.py", SCORING_1),
               Write("deploy/helm/values-prod.yaml", VALUES_2021),
           )),
    Commit("2021-12-08 11:20", "priya.r",
           "test: unit tests for the scoring rules, run in CI\n\n"
           "Covers channel base rates, signal weights, the 1.0 cap and the\n"
           "review/decline thresholds Fraud Risk signed off.",
           (
               Write("tests/__init__.py", ""),
               Write("tests/test_scoring.py", _scoring_era(T_SCORING_1)),
               Write(".github/workflows/ci.yml",
                     ci(py="3.9", checkout="v2", setup_python="v2", lint=False, compat=False, image=None)),
           )),
    Commit("2022-01-20 09:47", "alex.chen",
           "feat(metrics): Prometheus metrics on :9102\n\n"
           "Decisions by outcome and postings, so the Kafka / Consumers board can\n"
           "show throughput next to lag.",
           (
               Write(f"{SP}/metrics.py", _scoring_era(METRICS_1)),
               Write(f"{SP}/config.py", CONFIG_2021_METRICS),
               Write(f"{SP}/__main__.py", MAIN_2022),
               Edit(f"{SP}/consumer.py",
                    "from fraud_scoring.config import Settings\n",
                    "from fraud_scoring import metrics\nfrom fraud_scoring.config import Settings\n"),
               Edit(f"{SP}/consumer.py",
                    "            producer.poll(0)\n"
                    "            consumer.commit(message=msg, asynchronous=False)\n"
                    "    finally:",
                    "            producer.poll(0)\n"
                    "            consumer.commit(message=msg, asynchronous=False)\n"
                    "            metrics.DECISIONS.labels(assessment.outcome).inc()\n"
                    "            metrics.POSTINGS.inc()\n"
                    "    finally:"),
               Write("requirements.txt", requirements("1.7.0", prom="0.12.0", header=False)),
               Edit("deploy/helm/values-prod.yaml",
                    '  tag: ""\n\nresources:',
                    '  tag: ""\n\npodAnnotations:\n  prometheus.io/scrape: "true"\n'
                    '  prometheus.io/port: "9102"\n\nresources:'),
           )),
    Commit("2022-03-22 14:30", "priya.r",
           "feat: Avro and Schema Registry for both topics (ADR-0007)\n\n"
           "ADR-0007: card events are Avro, one Schema Registry subject per topic.\n"
           "We read cards.authorisation.requested.v1 with a reader schema pinned in\n"
           "schemas/, so a producer change cannot silently change what the scoring\n"
           "rules see. cards.ledger.posted.v1 is written with\n"
           "schemas/cards_ledger_posted_v1.avsc.\n\n"
           "Unreadable records are still logged and skipped, as with JSON.\n\n"
           "Refs: CARDS-1009",
           (
               Write(AUTH_AVSC, _auth_2022()),
               Write(LEDGER_AVSC, _ledger(decision=False, renamed=False)),
               Write(f"{SP}/__init__.py", _init("0.3.0", scoring=True)),
               Write(f"{SP}/config.py", CONFIG_2022),
               Write(f"{SP}/consumer.py", CONSUMER_2022_SKIP),
               Write("requirements.txt", requirements("1.8.2", fa="1.4.10", prom="0.12.0", header=False)),
               Write("Dockerfile", dockerfile("3.9", SP, user=False)),
               Edit("deploy/helm/values-prod.yaml",
                    "  CONSUMER_GROUP: fraud-scoring-consumer\n",
                    "  SCHEMA_REGISTRY_URL: http://kafka-dc1-registry.dss26.internal:8081\n"
                    "  CONSUMER_GROUP: fraud-scoring-consumer\n"),
               Edit("README.md", "- Records are JSON.",
                    "- Records are Avro, read with the reader schema pinned in `schemas/`\n"
                    "  ([ADR-0007](https://landoop.atlassian.net/wiki/spaces/DSS26/pages/3980034049/ADR-0007+Avro+and+Schema+Registry+for+card+events))."),
           )),
    Commit("2022-04-07 10:02", "alex.chen",
           "fix(consumer): never commit past a record we cannot read\n\n"
           "During the Avro cut-over on 2022-03-29 we skipped 214 records written\n"
           "with an unregistered schema. Each one was an authorisation with no\n"
           "score and no ledger posting, and finding them again took two days of\n"
           "reconciliation with Clearing.\n\n"
           "A record we cannot read has no amount we can trust. Approving it lets\n"
           "an unscored payment through, declining it fails a customer's card for\n"
           "no reason of theirs, skipping it leaves a hole in the ledger. So stop:\n"
           "seek back to the record, retry once a second and let the lag alert\n"
           "page a human.\n\n"
           "Refs: CARDS-1011",
           (
               Write(f"{SP}/consumer.py", CONSUMER_2022),
               Write(f"{SP}/metrics.py", _scoring_era(METRICS_2)),
               Write(f"{SP}/__init__.py", _init("0.4.0", scoring=True)),
               Edit("README.md", "## Running\n", FAIL_CLOSED_2022),
           )),
    Commit("2022-09-23 14:15", "tomasz.nowak",
           "ci: build and push the image from main\n\n"
           "Replaces the manual docker build on the deploy host. Images are tagged\n"
           "with the commit SHA; the release pipeline picks the tag.",
           (Write(".github/workflows/ci.yml",
                  ci(py="3.9", checkout="v2", setup_python="v2", lint=False, compat=False,
                     image="fraud-scoring", login="v2", build_push="v3")),)),
    Commit("2022-11-08 08:40", "tomasz.nowak",
           "chore(deploy): move production to cards-prod-euw1\n\n"
           "kafka-dc1 migration, cut-over window CHG-3120 (2022-11-08 06:00-07:00).\n"
           "fraud-scoring-consumer offsets were translated from the MirrorMaker 2\n"
           "checkpoints and checked per partition before the switch.",
           (
               Edit("deploy/helm/values-prod.yaml",
                    "# fraud-scoring - production (kafka-dc1).",
                    "# fraud-scoring - production (cards-prod-euw1)."),
               Edit("deploy/helm/values-prod.yaml",
                    "  KAFKA_BOOTSTRAP_SERVERS: kafka-dc1-broker-01.dss26.internal:9092,"
                    "kafka-dc1-broker-02.dss26.internal:9092,kafka-dc1-broker-03.dss26.internal:9092\n",
                    "  KAFKA_BOOTSTRAP_SERVERS: demo-kafka-prod:9092\n"),
               Edit("deploy/helm/values-prod.yaml",
                    "  SCHEMA_REGISTRY_URL: http://kafka-dc1-registry.dss26.internal:8081\n",
                    "  SCHEMA_REGISTRY_URL: http://demo-kafka-prod:8081\n"),
               Write("catalog-info.yaml", catalog("2022-11")),
           )),
    Commit("2022-12-07 15:20", "alex.chen",
           "feat(scoring): amount bands above 1,000 and 5,000 (RISK-118)\n\n"
           "Fraud Risk's Q4 review: high-value e-commerce with a new device was\n"
           "approved too often. Adds 0.10 from 1,000 and 0.25 from 5,000 (major\n"
           "units), highest band only.",
           (
               Write(f"{SP}/scoring.py", SCORING_2),
               Write("tests/test_scoring.py", _scoring_era(T_SCORING_2)),
           )),
    Commit("2023-02-23 10:05", "jordan.k",
           "chore: Python 3.11, confluent-kafka 2.0, ruff\n\n"
           "- python:3.11-slim base image, runs as a non-root user (image scan\n"
           "  finding PLAT-341)\n"
           "- confluent-kafka 1.8.2 -> 2.0.2, fastavro and prometheus-client to\n"
           "  current\n"
           "- ruff in CI; pytest picks the package up via pythonpath",
           (
               Write("Dockerfile", dockerfile("3.11", SP)),
               Write("requirements.txt", requirements("2.0.2", fa="1.7.1", prom="0.16.0")),
               Write("requirements-dev.txt", requirements_dev("7.2.1", ruff="0.0.252")),
               Write("pyproject.toml", pyproject("2023")),
               Write(".gitignore", gitignore(terraform=False)),
               Write(".github/workflows/ci.yml",
                     ci(py="3.11", checkout="v3", setup_python="v4", compat=False,
                        image="fraud-scoring", login="v2", build_push="v3")),
           )),
    Commit("2023-03-15 14:48", "jordan.k",
           "perf(consumer): batch consume, commit once per batch, hold only the blocked partition\n\n"
           "Per-record synchronous commits capped a pod at about 400 records/s, and\n"
           "one unreadable record slowed every other partition to one record a\n"
           "second while we sat on it.\n\n"
           "- consume up to BATCH_SIZE records, post them, wait for every ack, then\n"
           "  commit once per partition\n"
           "- an unreadable record pauses only its own partition; it is retried\n"
           "  every BLOCKED_RETRY_SECONDS and nothing past it is committed\n"
           "- consumer settings come from a properties file the chart renders from\n"
           "  kafka.consumer, so ops can tune them without a release\n"
           "- uat values added\n\n"
           "Load test in uat: 3,100 records/s per pod, p99 batch time 180 ms.\n\n"
           "Refs: CARDS-1016",
           (
               *_pkg(_scoring_era, PKG_BATCH_2023, SP),
               Write(f"{SP}/__init__.py", _init("1.0.0", scoring=True)),
               Write("tests/test_consumer.py", _scoring_era(T_CONSUMER_2023)),
               Write("tests/test_config.py", _scoring_era(T_CONFIG)),
               Write(".dockerignore", dockerignore(monitoring=False)),
               *_values_both("2023-03"),
           )),
    Commit("2023-05-19 11:05", "priya.r",
           "chore(schemas): sync the authorisation reader schema (adds tier)\n\n"
           "merchant-gateway added `tier` with a default. Records from the old\n"
           "writer still resolve; keep our reader in step so we can log it.",
           (Write(AUTH_AVSC, AUTH_FINAL),)),
    Commit("2023-06-22 11:12", "alex.chen",
           "chore(deploy): set session.timeout.ms to 45 s\n\n"
           "librdkafka 2.0 moved the default from 10 s to 45 s (KIP-735) and we\n"
           "were still pinning 10 s from the kafka-dc1 days. Match the client\n"
           "default and keep it explicit so an upgrade cannot change it under us.",
           _values_both("2023-06")),
    Commit("2023-07-10 14:02", "priya.r",
           "feat(scoring): cross-border weight for merchants outside the EEA (RISK-207)\n\n"
           "+0.10 when the merchant country is outside the EEA, GB and CH.",
           (
               Write(f"{SP}/scoring.py", SCORING_3),
               Write("tests/test_scoring.py", _scoring_era(T_SCORING_3)),
           )),
    Commit("2023-09-27 10:40", "jordan.k",
           "fix(ledger): derive posting_id from auth_id so a replay cannot double-post\n\n"
           "After the 2023-09-19 rebalance 1,180 authorisations were posted twice:\n"
           "the batch was produced, the commit failed, and the new owner of the\n"
           "partitions produced it again with fresh uuid4 ids. The General Ledger\n"
           "de-duplicates on posting_id, so make it a function of auth_id (uuid5,\n"
           "fixed namespace).\n\n"
           "Refs: CARDS-1019",
           (
               Write(f"{SP}/ledger.py", _scoring_era(LEDGER_2)),
               Write(f"{SP}/consumer.py", _scoring_era(F_CONSUMER)),
               Write("tests/test_ledger.py", _scoring_era(T_LEDGER_1)),
               Write("tests/test_consumer.py", _scoring_era(T_CONSUMER)),
           )),
    Commit("2023-11-14 09:12", "platform-bot",
           "chore(deps): bump prometheus-client from 0.16.0 to 0.19.0",
           (Edit("requirements.txt", "prometheus-client==0.16.0", "prometheus-client==0.19.0"),)),
    Commit("2024-01-16 09:05", "platform-bot",
           "chore(deps): bump confluent-kafka from 2.0.2 to 2.3.0",
           (Edit("requirements.txt", "confluent-kafka[avro]==2.0.2", "confluent-kafka[avro]==2.3.0"),)),
    Commit("2024-01-23 09:30", "platform-bot",
           "chore(deps): bump the github-actions group with 4 updates\n\n"
           "actions/checkout 3 -> 4, actions/setup-python 4 -> 5,\n"
           "docker/login-action 2 -> 3, docker/build-push-action 3 -> 5.\n"
           "Node 16 actions are deprecated on GitHub-hosted runners.",
           (Write(".github/workflows/ci.yml",
                  ci(py="3.11", compat=False, image="fraud-scoring", build_push="v5")),)),
    Commit("2024-02-15 16:20", "tomasz.nowak",
           "chore(deploy): max.poll.interval.ms 30 s so a hung pod gives up its partitions\n\n"
           "On 2024-02-08 a pod stuck in a Schema Registry call kept its partitions\n"
           "for the full five minutes before the group moved them. A healthy batch\n"
           "takes well under a second, so 30 s is plenty.",
           _values_both("2024-02")),
    Commit("2024-03-26 09:10", "platform-bot",
           "chore(deps): bump fastavro from 1.7.1 to 1.9.4",
           (Edit("requirements.txt", "fastavro==1.7.1", "fastavro==1.9.4"),)),
    Commit("2024-05-29 15:10", "alex.chen",
           "feat(ledger): carry the decision on every posting (ADR-0011)\n\n"
           "ADR-0011: this service now makes the approve/review/decline decision\n"
           "instead of handing a score to the issuer host. Postings carry it in a\n"
           "new `decision` field; the APPROVE default keeps the ledger schema\n"
           "BACKWARD compatible for readers still on the old version.\n\n"
           "Also round-trips records through both pinned schemas in the tests.\n\n"
           "Refs: CARDS-1038, CHG-4471",
           (
               Write(LEDGER_AVSC, _ledger(decision=True, renamed=False)),
               Write(f"{SP}/ledger.py", _scoring_era(F_LEDGER)),
               Write(f"{SP}/__init__.py", _init("1.4.0", scoring=True)),
               Write("tests/test_ledger.py", _scoring_era(T_LEDGER)),
           )),
    Commit("2024-06-06 10:20", "alex.chen",
           "refactor!: rename fraud-scoring to fraud-decisioning-svc (ADR-0011)\n\n"
           "Package, image, metrics and catalog entry move to the new name. The\n"
           "consumer group is NOT switched here: its offsets have to be copied\n"
           "first (next change, CHG-4502).\n\n"
           "Metric names change from fraud_scoring_* to fraud_decisioning_*; the\n"
           "Kafka / Consumers board shows both for two weeks.\n\n"
           "Refs: CARDS-1046",
           (
               *(Delete(f"{SP}/{name}") for name in OLD_PKG_FILES),
               *_pkg(_old_group, PKG_RENAMED, DP),
               Write("tests/test_config.py", _old_group(T_CONFIG)),
               Write("tests/test_consumer.py", T_CONSUMER),
               Write("tests/test_ledger.py", T_LEDGER),
               Write("tests/test_scoring.py", T_SCORING_3),
               Write("Dockerfile", dockerfile("3.11", DP)),
               Write("pyproject.toml", pyproject("2024")),
               Write(".github/workflows/ci.yml", ci(py="3.11", compat=False, build_push="v5")),
               Write("catalog-info.yaml", catalog("2024-06-04")),
               *_values_both("2024-06-04"),
           )),
    Commit("2024-06-11 07:45", "alex.chen",
           "chore(deploy): consume as fraud-decisioning-engine (ADR-0011)\n\n"
           "Offsets were copied from fraud-scoring-consumer to\n"
           "fraud-decisioning-engine with kafka-consumer-groups --reset-offsets\n"
           "--from-file inside the CHG-4502 window, with the deployment scaled to\n"
           "zero. fraud-scoring-consumer gets deleted once this has run clean for\n"
           "a week.",
           (
               Write(f"{DP}/config.py", CONFIG_PRE_INC),
               Write("tests/test_config.py", T_CONFIG),
               Write("catalog-info.yaml", catalog("2024-06-11")),
               *_values_both("2024-06-11"),
           )),
    Commit("2024-06-18 09:00", "platform-bot",
           "chore(deps): bump the dev-tools group with 2 updates\n\n"
           "pytest 7.2.1 -> 8.2.2, ruff 0.0.252 -> 0.4.8.",
           (Write("requirements-dev.txt", requirements_dev("8.2.2", ruff="0.4.8")),)),
    Commit("2024-06-24 14:30", "alex.chen",
           "docs: README for fraud-decisioning-svc; fraud-scoring-consumer deleted\n\n"
           "Finishes ADR-0011. The old group has been empty for a week and was\n"
           "deleted today. The ledger schema's doc strings follow the new name\n"
           "(doc-only change, compatible).",
           (
               Write("README.md", README_2024),
               Write(LEDGER_AVSC, LEDGER_FINAL),
               Write(".github/pull_request_template.md", PR_TEMPLATE),
           )),
    Commit("2024-07-09 09:00", "platform-bot",
           "chore(deps): bump docker/build-push-action from 5 to 6",
           (Edit(".github/workflows/ci.yml",
                 "docker/build-push-action@v5", "docker/build-push-action@v6"),)),
    Commit("2024-09-10 09:00", "platform-bot",
           "chore(deps): bump confluent-kafka from 2.3.0 to 2.5.0",
           (Edit("requirements.txt", "confluent-kafka[avro]==2.3.0", "confluent-kafka[avro]==2.5.0"),)),
    Commit("2024-10-17 10:30", "priya.r",
           "ci: check cards.ledger.posted.v1 against the registry on every PR\n\n"
           "Action item from INC-2024-09-12-003: every cards repo that owns a\n"
           "schema runs the shared schema-compat workflow from cards-ci-workflows\n"
           "before merge. We own the ledger posting schema. The authorisation\n"
           "schema here is our reader copy; merchant-gateway owns and checks it.",
           (Write(".github/workflows/ci.yml", ci(py="3.11")),)),
    Commit("2025-01-13 11:00", "jordan.k",
           "chore(deploy): scrape metrics with the Datadog OpenMetrics check\n\n"
           "Prometheus and Grafana for the cards services are being retired\n"
           "(PLAT-590). Datadog EU reads the same /metrics endpoint from the pod\n"
           "annotation; metric names are unchanged.",
           _values_both("2025-01")),
    Commit("2025-01-22 10:15", "jordan.k",
           "chore(deps): confluent-kafka patch updates only (PLAT-622)\n\n"
           "The Kafka platform team soaks every librdkafka minor in uat before\n"
           "Tier-1 consumers take it. The update bot keeps proposing patch\n"
           "releases; minors come through the platform team's upgrade ticket.",
           (
               Write("requirements.txt", requirements("2.5.0", fa="1.9.4", prom="0.19.0", hold=True)),
               Write("pyproject.toml", pyproject("2025-01")),
           )),
    Commit("2025-02-27 15:40", "alex.chen",
           "perf(runtime): collect garbage between batches, not during them\n\n"
           "p99 decision latency had 300-600 ms spikes that lined up with gen-2\n"
           "collections landing in the middle of a batch. Switch automatic GC off\n"
           "and collect between batches once enough allocations have piled up.\n"
           "uat: p99 back under 40 ms.\n\n"
           "Refs: CARDS-1251",
           (
               Write(f"{DP}/runtime.py", RUNTIME_GC),
               Write(f"{DP}/consumer.py", CONSUMER_GC),
               Write(f"{DP}/__main__.py", F_MAIN),
               Write(f"{DP}/__init__.py", _init("2.3.0")),
           )),
    Commit("2025-03-19 09:55", "jordan.k",
           "fix(consumer): raise max.poll.interval.ms to 5 min and re-enable automatic GC\n\n"
           "INC-2025-03-18-002: fraud-decisioning-engine lag peaked at 210,000\n"
           "while the group rebalanced every few minutes.\n\n"
           "With automatic GC off (2025-02-27) garbage piled up until\n"
           "collect_between_batches ran a full collection, which took 8-25 s on a\n"
           "loaded pod. Add a 2000-record batch and the gap between polls went past\n"
           "max.poll.interval.ms (30 s since 2024-02): the member was evicted, its\n"
           "partitions moved, and the next pod hit the same wall.\n\n"
           "- max.poll.interval.ms 30000 -> 300000 (prod and uat)\n"
           "- automatic GC back on; gc.freeze() after startup, gen-0 threshold 10,000\n"
           "- BATCH_SIZE 2000 -> 500\n"
           "- tests guard the deployed consumer settings\n\n"
           "Emergency change CHG-5038, approved by lena.fischer.",
           (
               Write(f"{DP}/runtime.py", F_RUNTIME),
               Write(f"{DP}/consumer.py", F_CONSUMER),
               Write(f"{DP}/config.py", F_CONFIG),
               Write(f"{DP}/__init__.py", _init("2.3.1")),
               Write("tests/test_deploy_values.py", T_DEPLOY),
               Write("requirements-dev.txt", requirements_dev("8.2.2", ruff="0.4.8", pyyaml=True)),
               *_values_both("2025-03"),
               Edit("README.md",
                    "`kafka.consumer`. Production changes need a CHG ticket.\n",
                    "`kafka.consumer`. Production changes need a CHG ticket.\n\n"
                    "`max.poll.interval.ms` was raised to 300000 after INC-2025-03-18-002\n"
                    "(rebalance storm). Do not lower it without a load test.\n"),
           )),
    Commit("2025-06-11 10:00", "lena.fischer",
           "chore(catalog): page through PagerDuty (PSVC42A)\n\n"
           "Cards Platform paging moves from Opsgenie to PagerDuty, escalation\n"
           "policy \"Cards Platform - Primary\". Links the Datadog dashboard.",
           (Write("catalog-info.yaml", catalog("2025-06")),)),
    Commit("2025-06-27 14:20", "priya.r",
           "chore: Python 3.12\n\n"
           "Base image, CI and requires-python. Moves ruff's rule selection under\n"
           "[tool.ruff.lint] to silence the deprecation warning.",
           (
               Write("Dockerfile", dockerfile("3.12", DP)),
               Write("pyproject.toml", pyproject("final")),
               Write(".github/workflows/ci.yml", ci()),
           )),
    Commit("2025-07-15 09:00", "platform-bot",
           "chore(deps): bump prometheus-client from 0.19.0 to 0.22.1",
           (Edit("requirements.txt", "prometheus-client==0.19.0", "prometheus-client==0.22.1"),)),
    Commit("2025-08-14 11:30", "jordan.k",
           "chore(deploy): request 1.5 GiB of memory in prod\n\n"
           "Since gc.freeze() RSS settles around 1.3 GiB at peak. With 1 GiB\n"
           "requests the scheduler kept packing pods onto nodes that then ran hot.",
           (Write("deploy/helm/values-prod.yaml", values("prod", "2025-08")),)),
    Commit("2025-09-19 15:00", "alex.chen",
           "fix(scoring): count a repeated risk signal once (RISK-341)\n\n"
           "merchant-gateway sometimes attaches NEW_DEVICE twice when two of its\n"
           "checks raise it. Each copy added 0.20, which pushed ordinary\n"
           "new-phone e-commerce into REVIEW.",
           (
               Write(f"{DP}/scoring.py", SCORING_4),
               Write(f"{DP}/__init__.py", _init("2.5.0")),
               Write("tests/test_scoring.py", T_SCORING),
           )),
    Commit("2025-11-18 09:00", "platform-bot",
           "chore(deps): bump fastavro from 1.9.4 to 1.12.1",
           (Edit("requirements.txt", "fastavro==1.9.4", "fastavro==1.12.1"),)),
    Commit("2026-01-22 10:40", "jordan.k",
           "feat(monitoring): manage the Datadog monitors as code\n\n"
           "Imported the existing kafka_consumer_lag monitor\n"
           "(terraform import datadog_monitor.kafka_consumer_lag 19283746) so\n"
           "threshold and routing changes get reviewed like code. Atlantis plans\n"
           "on the PR and applies after approval.",
           (
               Write("monitoring/versions.tf", src=f"{F}/monitoring/versions.tf"),
               Write("monitoring/monitors.tf", src=f"{F}/monitoring/monitors.tf"),
               Write("atlantis.yaml", ATLANTIS),
               Write(".gitignore", gitignore()),
               Write(".dockerignore", dockerignore()),
           )),
    Commit("2026-02-16 14:10", "alex.chen",
           "feat(scoring): weight VELOCITY_HIGH at 0.45 (RISK-388)\n\n"
           "Fraud Risk's January review of confirmed card-testing fraud: most\n"
           "cases carried VELOCITY_HIGH and still scored under 0.8. 0.40 -> 0.45.",
           (
               Write(f"{DP}/scoring.py", F_SCORING),
               Write(f"{DP}/__init__.py", _init("2.6.0")),
           )),
    Commit("2026-03-03 11:00", "alex.chen",
           "docs: refresh the README\n\n"
           "Fail-closed behaviour and what it looks like on the dashboards,\n"
           "configuration table, monitors, and the post-INC-2025-03-18-002\n"
           "consumer settings. Matches the Confluence service page.",
           (Write("README.md", src=f"{F}/README.md"),)),
    Commit("2026-05-12 10:15", "lena.fischer",
           "feat(monitoring): page on kafka_consumer_lag at 5,000, over 1 minute\n\n"
           "From the Datadog monitor review booked at the 2026-04-29 ops review.\n"
           "50,000 records is minutes of card authorisations waiting for a\n"
           "decision, and avg(last_5m) added more on top: in INC-2025-03-18-002\n"
           "the monitor fired 15 minutes after impact. max over the last minute\n"
           "fires as soon as 5,000 is crossed. Warning and recovery scale with\n"
           "it. The Confluence service page is updated to match.",
           (
               Edit("monitoring/monitors.tf",
                    "avg(last_5m):avg:kafka.consumer_lag", "max(last_1m):avg:kafka.consumer_lag"),
               Edit("monitoring/monitors.tf",
                    "by {consumer_group,topic} > 50000", "by {consumer_group,topic} > 5000"),
               Edit("monitoring/monitors.tf",
                    "critical          = 50000\n    critical_recovery = 10000\n    warning           = 20000",
                    "critical          = 5000\n    critical_recovery = 1000\n    warning           = 2000"),
               Edit("README.md",
                    "above 50,000 records of lag on", "above 5,000 records of lag on"),
           )),
    Commit("2026-06-16 09:00", "platform-bot",
           "chore(deps): bump the dev-tools group with 2 updates\n\n"
           "pytest 8.2.2 -> 8.4.2, ruff 0.4.8 -> 0.14.8.",
           (Write("requirements-dev.txt", requirements_dev("8.4.2", ruff="0.14.8", pyyaml=True)),)),
)


# ---------------------------------------------------------------------------
# Scenario pull requests
# ---------------------------------------------------------------------------

V2_TEST_SCHEMA = "tests/schemas/cards_authorisation_requested_v2_proposed.avsc"
V1_TEST_SCHEMA = "tests/schemas/cards_authorisation_requested_v1.avsc"

PRS: tuple[ScenarioPR, ...] = (
    ScenarioPR(
        key="fds-session-timeout",
        kind="decoy",
        scenario="consumer-lag",
        branch="jordan/session-timeout-failover",
        title="fix(consumer): lower session.timeout.ms to 10s for faster failover on node drain",
        body=(
            "## What\n"
            "Lower `session.timeout.ms` for `fraud-decisioning-engine` in prod from 45000 to 10000.\n\n"
            "## Why\n"
            "During the node-pool rotation this week two pods on drained nodes did not finish "
            "shutting down inside the grace period. Their partitions stayed assigned to members "
            "that were already gone until the 45 s session timeout ran out, and authorisations "
            "on those partitions waited the whole time. With 10 s the group notices a dead "
            "member four times faster.\n\n"
            "`heartbeat.interval.ms` stays at 3000, so 10 s is still more than three heartbeats "
            "(`test_heartbeat_fits_the_session_timeout` passes). `max.poll.interval.ms` is "
            "untouched and stays at 300000 (INC-2025-03-18-002).\n\n"
            "## Risk and rollout\n"
            "Consumer config only; the rollout restarts pods one at a time.\n"
            "- CHG: CHG-6207 (standard change)\n"
            "- Rollback: revert this PR.\n\n"
            "## Schema impact\n- [x] none"
        ),
        author="jordan.k",
        commit_message=(
            "fix(consumer): lower session.timeout.ms to 10s for faster failover on node drain\n\n"
            "A member that dies without leaving the group keeps its partitions until\n"
            "the session times out. 10 s is still more than three heartbeats (3000)."
        ),
        ops=(Edit("deploy/helm/values-prod.yaml",
                  "    session.timeout.ms: 45000\n", "    session.timeout.ms: 10000\n"),),
        labels=("tier-1", "consumer-config"),
    ),
    ScenarioPR(
        key="fds-confluent-kafka-253",
        kind="decoy",
        scenario="consumer-lag",
        branch="platform-bot/pip/confluent-kafka-2.5.3",
        title="chore(deps): bump confluent-kafka from 2.5.0 to 2.5.3",
        body=(
            "Bumps [confluent-kafka](https://github.com/confluentinc/confluent-kafka-python) "
            "from 2.5.0 to 2.5.3.\n\n"
            "Patch release; bundles librdkafka 2.5.3. Proposed because this repo allows patch "
            "updates only for confluent-kafka (see `requirements.txt`, PLAT-622).\n\n"
            "- Release notes: https://github.com/confluentinc/confluent-kafka-python/releases/tag/v2.5.3\n"
            "- Changelog: https://github.com/confluentinc/confluent-kafka-python/blob/master/CHANGELOG.md\n\n"
            "---\n"
            "This pull request was opened by dss26-platform-bot. Merge it after CI passes."
        ),
        author="platform-bot",
        commit_message="chore(deps): bump confluent-kafka from 2.5.0 to 2.5.3",
        ops=(Edit("requirements.txt",
                  "confluent-kafka[avro]==2.5.0\n", "confluent-kafka[avro]==2.5.3\n"),),
        labels=("dependencies",),
    ),
    ScenarioPR(
        key="fds-decimal-amount-reader",
        kind="open",
        scenario="consumer-lag",
        branch="alex/decimal-amount-reader",
        title="feat(consumer): accept decimal-string amount (CARDS-1502)",
        body=(
            "## What\n"
            "Consumer half of CARDS-1502.\n\n"
            "- The reader schema for `cards.authorisation.requested.v1` accepts `amount` as "
            "`double` (today's producers) **or** a decimal `string` (v2). Avro resolves either "
            "writer type onto the union, and `fraud_decisioning/amounts.py` parses both to "
            "`Decimal` before scoring.\n"
            "- `country` becomes optional (`[\"null\", \"string\"]`, default `null`). The v2 "
            "draft drops it, and with the current reader a missing country would silently read "
            "as `\"US\"`. Scoring records `COUNTRY_UNKNOWN` instead of guessing.\n"
            "- An amount we cannot parse (`\"12,50\"`, `NaN`, negative) is treated like any "
            "unreadable record: the partition holds (README, Fail closed).\n"
            "- `cards.ledger.posted.v1` is unchanged; `amount` stays `double` there until the "
            "ledger half of CARDS-1502.\n\n"
            "## Why\n"
            "Ops review 2026-04-29 agreed the order: fraud-decisioning reads v2 first, then "
            "merchant-gateway changes the producer schema. With the v1 reader pinned, the first "
            "v2 record cannot be read and its partition stops.\n\n"
            "**This has to be in production before merchant-gateway publishes v2.**\n\n"
            "## Testing\n"
            "- `tests/test_reader_schema.py`: records written with the v1 schema and with the "
            "proposed v2 schema (`tests/schemas/`) both decode with the new reader.\n"
            "- `tests/test_amounts.py`: parsing and refusal cases.\n\n"
            "## Before merge\n"
            "- [ ] Load test in uat at 2x peak. Union resolution and `Decimal` parsing add work "
            "per record; I want p99 batch time next to the current baseline (CARDS-1517).\n"
            "- [ ] CHG ticket for the prod rollout.\n\n"
            "## Schema impact\n"
            "- [x] reader schema (`schemas/cards_authorisation_requested_v1.avsc`)"
        ),
        author="alex.chen",
        commit_message=(
            "feat(consumer): accept decimal-string amount (CARDS-1502)\n\n"
            "The reader takes amount as double (v1) or decimal string (v2) and parses\n"
            "both to Decimal; country is optional. Consumer half of CARDS-1502: it\n"
            "has to ship before merchant-gateway publishes v2."
        ),
        ops=(
            Edit(AUTH_AVSC,
                 '      "name": "amount",\n'
                 '      "type": "double",\n'
                 '      "doc": "Authorization amount in the transaction currency, major units."\n',
                 '      "name": "amount",\n'
                 '      "type": [\n'
                 '        "double",\n'
                 '        "string"\n'
                 '      ],\n'
                 '      "doc": "Authorization amount in the transaction currency, major units. '
                 'double from v1 producers, decimal string from v2 (CARDS-1502)."\n'),
            Edit(AUTH_AVSC,
                 '      "name": "country",\n'
                 '      "type": "string",\n'
                 '      "doc": "ISO-3166 alpha-2 country code of the merchant.",\n'
                 '      "default": "US"\n',
                 '      "name": "country",\n'
                 '      "type": [\n'
                 '        "null",\n'
                 '        "string"\n'
                 '      ],\n'
                 '      "doc": "ISO-3166 alpha-2 country code of the merchant. Optional: v2 '
                 'producers do not send it (CARDS-1502).",\n'
                 '      "default": null\n'),
            Write(f"{DP}/amounts.py", src=f"{F}/_pr/amounts.py"),
            Edit(f"{DP}/serde.py",
                 "from confluent_kafka.serialization import MessageField, SerializationContext\n",
                 "from confluent_kafka.serialization import MessageField, SerializationContext\n\n"
                 "from fraud_decisioning.amounts import normalise\n"),
            Edit(f"{DP}/serde.py",
                 "            raise EmptyRecordError(f\"null value at {msg.topic()}[{msg.partition()}]@{msg.offset()}\")\n"
                 "        return value\n",
                 "            raise EmptyRecordError(f\"null value at {msg.topic()}[{msg.partition()}]@{msg.offset()}\")\n"
                 "        # amount is a double (v1) or a decimal string (v2, CARDS-1502). An\n"
                 "        # amount we cannot parse raises here and holds the partition.\n"
                 "        return normalise(value)\n"),
            Edit(f"{DP}/scoring.py",
                 "from dataclasses import dataclass\nfrom typing import Any\n",
                 "from dataclasses import dataclass\nfrom decimal import Decimal\nfrom typing import Any\n\n"
                 "from fraud_decisioning.amounts import parse_amount\n"),
            Edit(f"{DP}/scoring.py",
                 "AMOUNT_BANDS = ((5000.0, 0.25), (1000.0, 0.10))",
                 'AMOUNT_BANDS = ((Decimal("5000"), 0.25), (Decimal("1000"), 0.10))'),
            Edit(f"{DP}/scoring.py",
                 '    amount = float(auth["amount"])\n',
                 '    amount = parse_amount(auth["amount"])\n'),
            Edit(f"{DP}/scoring.py",
                 '        reasons.append("CROSS_BORDER")\n',
                 '        reasons.append("CROSS_BORDER")\n'
                 "    elif not country:\n"
                 "        # v2 producers do not send country (CARDS-1502). Record it rather\n"
                 "        # than guess a home market.\n"
                 '        reasons.append("COUNTRY_UNKNOWN")\n'),
            Edit(f"{DP}/ledger.py",
                 '        "amount": float(auth["amount"]),\n',
                 "        # cards.ledger.posted.v1 keeps amount as a double until the ledger\n"
                 "        # half of CARDS-1502.\n"
                 '        "amount": float(auth["amount"]),\n'),
            Write(V1_TEST_SCHEMA, AUTH_FINAL),
            Write(V2_TEST_SCHEMA, _v2_proposed()),
            Write("tests/test_amounts.py", src=f"{F}/_pr/test_amounts.py"),
            Write("tests/test_reader_schema.py", src=f"{F}/_pr/test_reader_schema.py"),
            Edit("README.md",
                 "Producers may add fields with defaults without telling us.",
                 "Since CARDS-1502 the reader accepts `amount` as a double (v1) or a decimal\n"
                 "string (v2) and parses both to `Decimal`; `country` is optional.\n\n"
                 "Producers may add fields with defaults without telling us."),
        ),
        labels=("tier-1", "schema", "needs-load-test"),
    ),
)


REPO_SPEC = RepoSpec(
    name=REPO,
    description="Tier-1 fraud decisioning for card authorisations: consumes "
                "cards.authorisation.requested.v1, posts to cards.ledger.posted.v1.",
    team="cards-platform",
    domain="cards",
    tier="A",
    topics=("kafka", "python", "fraud-decisioning", "team-cards-platform", "domain-cards", "tier-1"),
    history=HISTORY,
    prs=PRS,
    labels=DEFAULT_LABELS + (
        Label("schema", "5319e7", "Avro schema or reader change"),
        Label("consumer-config", "c5def5", "Kafka consumer settings"),
        Label("needs-load-test", "fbca04", "Waiting on a uat load test before merge"),
    ),
    team_access=(("platform-engineering", "push"), ("risk-platform", "triage"),
                 ("payments-edge", "triage")),
)
