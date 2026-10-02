import pytest

from fraud_decisioning.scoring import APPROVE, DECLINE, REVIEW, assess, outcome_for


def auth(**overrides):
    base = {
        "auth_id": "a-1",
        "merchant_id": "mch_204",
        "amount": 42.5,
        "currency": "EUR",
        "country": "FR",
        "channel": "CARD_PRESENT",
        "risk_signals": [],
    }
    base.update(overrides)
    return base


def test_card_present_without_signals_is_approved():
    result = assess(auth())
    assert result.outcome == APPROVE
    assert result.score == pytest.approx(0.05)
    assert result.reasons == ()


def test_velocity_ok_is_not_a_risk():
    assert assess(auth(risk_signals=["VELOCITY_OK"])).score == pytest.approx(0.05)


def test_geo_mismatch_and_new_device_on_ecom_goes_to_review():
    result = assess(auth(channel="ECOM", risk_signals=["GEO_MISMATCH", "NEW_DEVICE"]))
    assert result.score == pytest.approx(0.65)
    assert result.outcome == REVIEW
    assert result.reasons == ("GEO_MISMATCH", "NEW_DEVICE")


def test_high_velocity_new_device_high_value_is_declined():
    result = assess(
        auth(channel="ECOM", amount=6200.0, risk_signals=["VELOCITY_HIGH", "NEW_DEVICE"])
    )
    assert result.outcome == DECLINE
    assert "AMOUNT_GE_5000" in result.reasons


def test_only_the_highest_amount_band_counts():
    assert assess(auth(amount=1500.0)).reasons == ("AMOUNT_GE_1000",)
    assert assess(auth(amount=9000.0)).reasons == ("AMOUNT_GE_5000",)


def test_unknown_signal_still_counts():
    assert assess(auth(risk_signals=["BIN_RANGE_PROBE"])).score == pytest.approx(0.25)


def test_repeated_signal_counts_once():
    once = assess(auth(risk_signals=["NEW_DEVICE"]))
    twice = assess(auth(risk_signals=["NEW_DEVICE", "new_device"]))
    assert once.score == twice.score


def test_cross_border_merchant():
    result = assess(auth(country="US"))
    assert result.reasons == ("CROSS_BORDER",)
    assert result.score == pytest.approx(0.15)


def test_unknown_channel_uses_the_default_base():
    assert assess(auth(channel="KIOSK")).score == pytest.approx(0.15)


def test_score_is_capped_at_one():
    result = assess(
        auth(
            channel="MOTO",
            amount=20000.0,
            country="US",
            risk_signals=["VELOCITY_HIGH", "GEO_MISMATCH", "NEW_DEVICE", "BIN_RANGE_PROBE"],
        )
    )
    assert result.score == 1.0
    assert result.outcome == DECLINE


@pytest.mark.parametrize(
    ("score", "outcome"),
    [(0.0, APPROVE), (0.4999, APPROVE), (0.5, REVIEW), (0.7999, REVIEW), (0.8, DECLINE)],
)
def test_thresholds(score, outcome):
    assert outcome_for(score) == outcome
