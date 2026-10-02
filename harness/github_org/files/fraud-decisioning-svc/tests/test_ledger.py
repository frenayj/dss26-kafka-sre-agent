import io
import json
from pathlib import Path

import fastavro
from fastavro.validation import validate

from fraud_decisioning.ledger import posting_id_for, to_posting
from fraud_decisioning.scoring import assess

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def parsed(name: str):
    return fastavro.parse_schema(json.loads((SCHEMAS / name).read_text()))


READER = parsed("cards_authorisation_requested_v1.avsc")
LEDGER = parsed("cards_ledger_posted_v1.avsc")

AUTH = {
    "auth_id": "6c1f9a52-0d3e-4b7a-9e21-8f4c3b2d1a90",
    "card_token": "tok_9f8e7d6c",
    "merchant_id": "mch_3381",
    "amount": 87.15,
    "currency": "EUR",
    "country": "DE",
    "ts": 1758270000000,
    "risk_signals": ["NEW_DEVICE"],
    "channel": "ECOM",
    "tier": "prod",
}


def test_posting_id_is_stable_per_authorisation():
    assert posting_id_for(AUTH["auth_id"]) == posting_id_for(AUTH["auth_id"])
    assert posting_id_for(AUTH["auth_id"]) != posting_id_for("another-auth")


def test_posting_carries_the_authorisation_and_the_decision():
    assessment = assess(AUTH)
    posting = to_posting(AUTH, assessment, now_ms=1758270000500)
    assert posting == {
        "posting_id": posting_id_for(AUTH["auth_id"]),
        "auth_id": AUTH["auth_id"],
        "merchant_id": "mch_3381",
        "amount": 87.15,
        "currency": "EUR",
        "risk_score": assessment.score,
        "decision": assessment.outcome,
        "ts": 1758270000500,
    }


def test_posting_matches_the_ledger_schema():
    posting = to_posting(AUTH, assess(AUTH), now_ms=1758270000500)
    assert validate(posting, LEDGER)


def test_round_trip_through_the_pinned_reader_schema():
    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, READER, AUTH)
    buf.seek(0)
    decoded = fastavro.schemaless_reader(buf, READER, READER)

    posting = to_posting(decoded, assess(decoded), now_ms=1758270000500)
    assert validate(posting, LEDGER)
    assert posting["amount"] == AUTH["amount"]
