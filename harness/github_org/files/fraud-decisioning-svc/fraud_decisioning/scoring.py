"""Rule-based risk scoring for card authorisations.

The score runs from 0.0 (nothing suspicious) to 1.0. It is the sum of a
channel base rate, an amount band, a cross-border weight and one weight per
risk signal the merchant gateway attached, capped at 1.0.

Weights and thresholds are owned by Fraud Risk (risk-platform). Change them
only with a RISK- ticket that names the expected approve/review/decline mix.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

APPROVE = "APPROVE"
REVIEW = "REVIEW"
DECLINE = "DECLINE"

REVIEW_AT = 0.5
DECLINE_AT = 0.8

CHANNEL_BASE = {
    "CARD_PRESENT": 0.05,
    "RECURRING": 0.05,
    "ECOM": 0.15,
    "MOTO": 0.20,
}
UNKNOWN_CHANNEL_BASE = 0.15

SIGNAL_WEIGHTS = {
    "VELOCITY_OK": 0.0,
    "NEW_DEVICE": 0.20,
    "GEO_MISMATCH": 0.30,
    "VELOCITY_HIGH": 0.45,
}
# A code the gateway starts sending before Fraud Risk has weighed it still
# counts for something.
UNKNOWN_SIGNAL_WEIGHT = 0.20

# (lower bound in major units, weight), highest band first.
AMOUNT_BANDS = ((5000.0, 0.25), (1000.0, 0.10))

CROSS_BORDER_WEIGHT = 0.10
# Merchant countries treated as domestic: the EEA, plus GB and CH (RISK-207).
DOMESTIC_COUNTRIES = frozenset(
    "AT BE BG CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT LU LV MT NL NO "
    "PL PT RO SE SI SK".split()
)


@dataclass(frozen=True)
class Assessment:
    score: float
    outcome: str
    reasons: tuple[str, ...]


def outcome_for(score: float) -> str:
    if score >= DECLINE_AT:
        return DECLINE
    if score >= REVIEW_AT:
        return REVIEW
    return APPROVE


def _signals(raw: Any) -> Iterable[str]:
    if not raw:
        return ()
    # De-duplicate: the gateway occasionally repeats a code when two of its
    # checks raise the same signal.
    return dict.fromkeys(str(s).upper() for s in raw)


def assess(auth: Mapping[str, Any]) -> Assessment:
    reasons: list[str] = []
    channel = str(auth.get("channel") or "")
    score = CHANNEL_BASE.get(channel, UNKNOWN_CHANNEL_BASE)

    amount = float(auth["amount"])
    for floor, weight in AMOUNT_BANDS:
        if amount >= floor:
            score += weight
            reasons.append(f"AMOUNT_GE_{int(floor)}")
            break

    country = auth.get("country")
    if country and country not in DOMESTIC_COUNTRIES:
        score += CROSS_BORDER_WEIGHT
        reasons.append("CROSS_BORDER")

    for signal in _signals(auth.get("risk_signals")):
        weight = SIGNAL_WEIGHTS.get(signal, UNKNOWN_SIGNAL_WEIGHT)
        if weight:
            score += weight
            reasons.append(signal)

    score = round(min(score, 1.0), 4)
    return Assessment(score=score, outcome=outcome_for(score), reasons=tuple(reasons))
