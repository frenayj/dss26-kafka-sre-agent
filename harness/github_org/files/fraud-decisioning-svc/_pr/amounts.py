"""Authorisation amounts as Decimal.

cards.authorisation.requested.v1 carries ``amount`` as a double today. From v2
(CARDS-1502) merchant-gateway sends it as a decimal string in major units, for
example ``"1499.90"``, so no precision is lost between the terminal and the
ledger. The reader schema accepts both; this module turns either into a
Decimal.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


class AmountError(ValueError):
    """The amount cannot be used to decide an authorisation."""


def parse_amount(raw: Any) -> Decimal:
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, bool):  # bool is an int subclass, never an amount
        raise AmountError(f"amount {raw!r} is not a number")
    elif isinstance(raw, float):
        # repr() keeps the shortest decimal that round-trips: 87.15, not
        # 87.150000000000005684...
        value = Decimal(repr(raw))
    elif isinstance(raw, int):
        value = Decimal(raw)
    elif isinstance(raw, str):
        try:
            value = Decimal(raw.strip())
        except InvalidOperation:
            raise AmountError(f"amount {raw!r} is not a decimal string") from None
    else:
        raise AmountError(f"amount has unexpected type {type(raw).__name__}")
    if not value.is_finite() or value < 0:
        raise AmountError(f"amount {raw!r} is not a finite, non-negative number")
    return value


def normalise(auth: dict[str, Any]) -> dict[str, Any]:
    """Parse ``amount`` in place. AmountError holds the partition, like any unreadable record."""
    auth["amount"] = parse_amount(auth["amount"])
    return auth
