from decimal import Decimal

import pytest

from fraud_decisioning.amounts import AmountError, normalise, parse_amount


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (87.15, Decimal("87.15")),
        ("87.15", Decimal("87.15")),
        (" 1499.90 ", Decimal("1499.90")),
        (12, Decimal("12")),
        ("0", Decimal("0")),
        (Decimal("5.00"), Decimal("5.00")),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["12,50", "", "NaN", "Infinity", "-3.00", -1.0, True, None])
def test_unusable_amounts_are_refused(raw):
    with pytest.raises(AmountError):
        parse_amount(raw)


def test_normalise_parses_in_place():
    auth = {"auth_id": "a-1", "amount": "42.10"}
    assert normalise(auth)["amount"] == Decimal("42.10")
    assert auth["amount"] == Decimal("42.10")
