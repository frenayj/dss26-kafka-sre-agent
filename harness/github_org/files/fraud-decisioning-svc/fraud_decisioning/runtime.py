"""Process-level tuning for the decisioning loop.

INC-2025-03-18-002: in February 2025 automatic GC was switched off and a full
collection ran between batches instead. On a large heap those collections took
seconds; with 2000-record batches the gap between polls went past
max.poll.interval.ms (30 s at the time), members were evicted and the group
rebalanced every few minutes. Automatic collection is back on. Objects that
live for the whole process (modules, schemas, clients) are frozen out of the
collector after startup, and gen-0 runs less often than the default 700.
"""

from __future__ import annotations

import gc

GEN0_THRESHOLD = 10_000


def tune_gc() -> None:
    """Call once, after startup allocations and before the loop starts."""
    gc.collect()
    gc.freeze()
    _, gen1, gen2 = gc.get_threshold()
    gc.set_threshold(GEN0_THRESHOLD, gen1, gen2)
