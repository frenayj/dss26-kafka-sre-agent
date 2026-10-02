"""Map a decided authorisation to a ``cards.ledger.posted.v1`` record."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from fraud_decisioning.scoring import Assessment

# Fixed namespace for posting ids. Never change it: the General Ledger
# de-duplicates on posting_id, and a new namespace would make every replayed
# authorisation look like a new posting.
POSTING_NAMESPACE = uuid.UUID("5b0e7c2a-91d4-4f3e-8a66-2c7d0f9e4b18")


def posting_id_for(auth_id: str) -> str:
    """Same authorisation, same posting id - a replay cannot double-post."""
    return str(uuid.uuid5(POSTING_NAMESPACE, auth_id))


def to_posting(auth: Mapping[str, Any], assessment: Assessment, now_ms: int) -> dict[str, Any]:
    return {
        "posting_id": posting_id_for(auth["auth_id"]),
        "auth_id": auth["auth_id"],
        "merchant_id": auth["merchant_id"],
        "amount": float(auth["amount"]),
        "currency": auth["currency"],
        "risk_score": assessment.score,
        "decision": assessment.outcome,
        "ts": now_ms,
    }
