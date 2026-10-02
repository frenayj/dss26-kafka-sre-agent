"""The reader schema resolves records from v1 writers and from the proposed v2 (CARDS-1502)."""

import io
import json
from decimal import Decimal
from pathlib import Path

import fastavro
import pytest

from fraud_decisioning.amounts import AmountError, normalise
from fraud_decisioning.ledger import to_posting
from fraud_decisioning.scoring import assess

ROOT = Path(__file__).resolve().parent.parent


def parsed(path: Path):
    return fastavro.parse_schema(json.loads(path.read_text()))


READER = parsed(ROOT / "schemas" / "cards_authorisation_requested_v1.avsc")
V1_WRITER = parsed(ROOT / "tests" / "schemas" / "cards_authorisation_requested_v1.avsc")
V2_WRITER = parsed(ROOT / "tests" / "schemas" / "cards_authorisation_requested_v2_proposed.avsc")

COMMON = {
    "auth_id": "0f7c2d9e-5a41-4c3b-9b8e-1d6a2f4e7c05",
    "card_token": "tok_51ab90",
    "merchant_id": "mch_7710",
    "currency": "EUR",
    "ts": 1777280400000,
    "risk_signals": [],
    "channel": "ECOM",
    "tier": "prod",
}


def read(writer, record):
    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, writer, record)
    buf.seek(0)
    return normalise(fastavro.schemaless_reader(buf, writer, READER))


def test_v1_record_reads_as_before():
    auth = read(V1_WRITER, {**COMMON, "amount": 87.15, "country": "DE"})
    assert auth["amount"] == Decimal("87.15")
    assert auth["country"] == "DE"
    assert assess(auth).reasons == ()


def test_v2_record_with_decimal_string_and_no_country():
    auth = read(V2_WRITER, {**COMMON, "amount": "1499.90"})
    assert auth["amount"] == Decimal("1499.90")
    assert auth["country"] is None

    assessment = assess(auth)
    assert assessment.reasons == ("AMOUNT_GE_1000", "COUNTRY_UNKNOWN")
    assert to_posting(auth, assessment, now_ms=1777280400500)["amount"] == 1499.90


def test_v2_record_with_an_unparseable_amount_is_refused():
    with pytest.raises(AmountError):
        read(V2_WRITER, {**COMMON, "amount": "1.499,90"})
