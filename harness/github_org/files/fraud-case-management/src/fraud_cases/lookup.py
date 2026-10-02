"""Who does an authorisation belong to? Score events only carry the auth_id."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class CardOwner:
    card_token: str
    customer_id: str


class CardOwnerLookup:
    def __init__(self, txn_history_url: str, card_lifecycle_url: str, timeout: float = 2.0) -> None:
        self._http = httpx.Client(timeout=timeout)
        self._txn_history_url = txn_history_url.rstrip("/")
        self._card_lifecycle_url = card_lifecycle_url.rstrip("/")

    def for_auth(self, auth_id: str) -> CardOwner:
        tx = self._http.get(f"{self._txn_history_url}/v1/transactions/{auth_id}")
        tx.raise_for_status()
        card_token = tx.json()["cardToken"]
        card = self._http.get(f"{self._card_lifecycle_url}/v1/cards/{card_token}")
        card.raise_for_status()
        return CardOwner(card_token=card_token, customer_id=card.json()["customerId"])

    def close(self) -> None:
        self._http.close()
