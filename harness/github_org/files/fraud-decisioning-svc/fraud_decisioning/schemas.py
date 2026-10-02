"""Load the Avro schemas the service pins.

Parsing at startup means a broken schema file fails the rollout, not the
first record.
"""

from __future__ import annotations

import json
from pathlib import Path

import fastavro


def load(path: Path) -> str:
    text = Path(path).read_text()
    fastavro.parse_schema(json.loads(text))
    return text
