"""Where the servers write what the agent published: ``<repo-root>/logs/``.

Every write is appended to a log whatever the back-end: with a fixture
back-end it is the output, with a live one it is the audit trail of what the
agent tried to publish.
"""

from __future__ import annotations

from pathlib import Path

from agent.config import REPO_ROOT

LOGS_DIR = REPO_ROOT / "logs"


def ensure_logs_dir() -> Path:
    """Make sure ``logs/`` exists and return its path."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR
