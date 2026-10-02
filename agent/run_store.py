"""SQLite-backed run history.

One process-wide store opened in ``server.py``'s ASGI lifespan, bound to
``logs/runs.db``. Two tables:

* ``runs``    - one row per supervisor invocation. Header (id, preset,
                 incident_id, prompt, timing, terminal status) + a cached
                 ``tool_call_count`` so the history list doesn't have to
                 scan ``events`` for every entry.
* ``events``  - one row per translated SSE frame, append-only and indexed
                 by ``(run_id, seq)``. The ``payload`` column carries the
                 same JSON dict the live ``/run`` stream emits, so replay
                 is "open this run's events as SSE in seq order" - the
                 frontend reducer doesn't care which one it's reading.

The store is concurrency-safe under FastAPI's threadpool: one
``sqlite3.Connection`` opened with ``check_same_thread=False``, all writes
guarded by a single re-entrant lock, WAL journal mode so concurrent reads
don't block. At our scale (~200 events/run, ~5 writes/sec peak) this is
trivially fast and avoids per-request connection setup.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id              TEXT PRIMARY KEY,
  preset          TEXT NOT NULL,
  incident_id     TEXT NOT NULL,
  prompt          TEXT NOT NULL,
  status          TEXT NOT NULL,
  started_at      INTEGER NOT NULL,
  ended_at        INTEGER,
  error_type      TEXT,
  error_message   TEXT,
  tool_call_count INTEGER NOT NULL DEFAULT 0,
  input_tokens    INTEGER NOT NULL DEFAULT 0,
  output_tokens   INTEGER NOT NULL DEFAULT 0,
  latency_ms      INTEGER NOT NULL DEFAULT 0,
  name            TEXT
);

CREATE INDEX IF NOT EXISTS runs_started ON runs(started_at DESC);

CREATE TABLE IF NOT EXISTS events (
  run_id  TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  seq     INTEGER NOT NULL,
  at      INTEGER NOT NULL,
  kind    TEXT NOT NULL,
  source  TEXT,
  payload TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);
"""


def now_ms() -> int:
    """Wall-clock milliseconds - shared between RunStore and server.emit()."""
    return int(time.time() * 1000)


class RunStore:
    """Thread-safe handle to ``logs/runs.db``."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; we drive transactions explicitly
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        # Per-run set of tool-use ids already counted. Strands re-emits
        # ``current_tool_use`` on every input-JSON delta, so one logical tool
        # call arrives as many ``"tool"`` frames sharing a single id. We count
        # distinct ids (the same key the live UI's toolCalls Map dedupes on)
        # rather than raw frames, which otherwise inflates the count ~100x.
        self._seen_tool_ids: Dict[str, set] = {}
        self._rename_legacy_column()
        self._conn.executescript(_SCHEMA)
        self._lock = threading.RLock()

    def _rename_legacy_column(self) -> None:
        """Databases from before ``incident_id`` called the column ``fixture``."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(runs)")}
        if "fixture" in cols:
            self._conn.execute("ALTER TABLE runs RENAME COLUMN fixture TO incident_id")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    # ---- writes ----------------------------------------------------------

    def create_run(
        self, *, preset: str, incident_id: str, prompt: str, name: Optional[str] = None
    ) -> str:
        run_id = str(uuid.uuid4())
        with self._tx() as cx:
            cx.execute(
                """
                INSERT INTO runs (id, preset, incident_id, prompt, status, started_at, name)
                VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (run_id, preset, incident_id, prompt, now_ms(), name),
            )
        return run_id

    def set_run_name(self, run_id: str, name: Optional[str]) -> bool:
        """Set or clear the user-facing display name. Returns True if a row was updated."""
        clean = name.strip() if isinstance(name, str) else None
        if clean == "":
            clean = None
        with self._lock:
            cur = self._conn.execute(
                "UPDATE runs SET name = ? WHERE id = ?",
                (clean, run_id),
            )
            return cur.rowcount > 0

    def append_event(
        self,
        run_id: str,
        *,
        seq: int,
        kind: str,
        source: Optional[str],
        payload: Dict[str, Any],
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (run_id, seq, at, kind, source, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, seq, now_ms(), kind, source, json.dumps(payload, default=str)),
            )
            if kind == "tool":
                # Count distinct tool-use ids, not raw frames: Strands re-emits
                # ``current_tool_use`` per input-JSON delta, so one call streams
                # many "tool" frames under a single id.
                tool_id = payload.get("id")
                seen = self._seen_tool_ids.setdefault(run_id, set())
                if tool_id is None or tool_id not in seen:
                    if tool_id is not None:
                        seen.add(tool_id)
                    self._conn.execute(
                        "UPDATE runs SET tool_call_count = tool_call_count + 1 WHERE id = ?",
                        (run_id,),
                    )
            elif kind == "metrics":
                # Sum across supervisor + every sub-agent. The five metrics
                # frames per run are non-overlapping (each agent owns its own
                # EventLoopMetrics) so plain addition is correct.
                self._conn.execute(
                    """
                    UPDATE runs
                       SET input_tokens  = input_tokens  + ?,
                           output_tokens = output_tokens + ?,
                           latency_ms    = latency_ms    + ?
                     WHERE id = ?
                    """,
                    (
                        int(payload.get("inputTokens", 0) or 0),
                        int(payload.get("outputTokens", 0) or 0),
                        int(payload.get("latencyMs", 0) or 0),
                        run_id,
                    ),
                )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE runs
                   SET status = ?, ended_at = ?, error_type = ?, error_message = ?
                 WHERE id = ?
                """,
                (status, now_ms(), error_type, error_message, run_id),
            )
            # The run is closed; drop its dedup set so the map doesn't grow
            # unbounded across many runs in one server lifetime.
            self._seen_tool_ids.pop(run_id, None)

    def delete_run(self, run_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            self._seen_tool_ids.pop(run_id, None)
            return cur.rowcount > 0

    # ---- reads -----------------------------------------------------------

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, preset, incident_id, status, started_at, ended_at,
                       error_type, error_message, tool_call_count,
                       input_tokens, output_tokens, latency_ms, name
                  FROM runs
                 ORDER BY started_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT r.id, r.preset, r.incident_id, r.prompt, r.status,
                       r.started_at, r.ended_at, r.error_type, r.error_message,
                       r.tool_call_count,
                       r.input_tokens, r.output_tokens, r.latency_ms, r.name,
                       (SELECT COUNT(*) FROM events WHERE run_id = r.id) AS event_count
                  FROM runs r
                 WHERE r.id = ?
                """,
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    # ---- events ----------------------------------------------------------

    def start_payload(self, run_id: str) -> Dict[str, Any]:
        """The payload of the run's stored ``start`` frame, or {} if none."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM events WHERE run_id = ? AND seq = 0 AND kind = 'start'",
                (run_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else {}

    def iter_events(self, run_id: str, after_seq: int = -1) -> Iterator[Dict[str, Any]]:
        """Yield events in seq order. Caller is responsible for streaming them.

        ``after_seq`` skips everything up to and including that seq, so a
        follower of a run in progress can fetch just the frames it hasn't seen.
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT seq, at, kind, source, payload
                  FROM events
                 WHERE run_id = ? AND seq > ?
                 ORDER BY seq
                """,
                (run_id, after_seq),
            )
            rows = cursor.fetchall()
        for row in rows:
            yield {
                "seq": row["seq"],
                "at": row["at"],
                "kind": row["kind"],
                "source": row["source"],
                "payload": json.loads(row["payload"]),
            }
