"""Postgres persistence for cases (schema in migrations/)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


class CaseStore:
    def __init__(self, database_url: str) -> None:
        self._conn = psycopg.connect(database_url, row_factory=dict_row)

    def open_case(self, *, customer_id: str, card_token: str, trigger: str, priority: str,
                  triggering_auth_id: str | None) -> dict | None:
        """Insert a case; returns None when this auth already has one (redelivery)."""
        with self._conn.transaction():
            row = self._conn.execute(
                """
                INSERT INTO fraud_case (case_id, customer_id, card_token, trigger, priority,
                                        triggering_auth_id, status, opened_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'OPEN', %s)
                ON CONFLICT (triggering_auth_id) DO NOTHING
                RETURNING *
                """,
                (str(uuid.uuid4()), customer_id, card_token, trigger, priority, triggering_auth_id,
                 datetime.now(timezone.utc)),
            ).fetchone()
        return row

    def resolve_case(self, case_id: str, *, outcome: str, actions: list[str], loss_amount: Decimal,
                     currency: str) -> dict | None:
        with self._conn.transaction():
            return self._conn.execute(
                """
                UPDATE fraud_case
                   SET status = 'RESOLVED', outcome = %s, actions_taken = %s, loss_amount = %s,
                       currency = %s, resolved_at = %s
                 WHERE case_id = %s AND status = 'OPEN'
                RETURNING *
                """,
                (outcome, actions, loss_amount, currency, datetime.now(timezone.utc), case_id),
            ).fetchone()
