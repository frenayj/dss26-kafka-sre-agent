"""Decide whether a fraud score deserves a human, and how urgently.

Pure functions only: this is the part analysts argue about, so it is the part
with the tests.
"""

from __future__ import annotations

from dataclasses import dataclass

# Rules from the decisioning engine that always merit a faster look.
HIGH_RISK_RULES = frozenset({"ACCOUNT_TAKEOVER", "CARD_TESTING", "MULE_PATTERN", "SIM_SWAP_RECENT"})


@dataclass(frozen=True)
class TriageResult:
    open_case: bool
    priority: str | None = None
    trigger: str = "MODEL_SCORE"


def triage(score: float, decision: str, rule_matches: list[str], review_threshold: float = 0.5) -> TriageResult:
    """Map one fraud.score.computed.v1 record to a case decision.

    DECLINE always opens a case (the cardholder may call). REVIEW opens one,
    faster when a high-risk rule fired. APPROVE opens nothing, unless the score
    sits above the review threshold - the engine and the threshold disagree,
    and that is worth a look at the lowest priority.
    """
    high_risk = bool(HIGH_RISK_RULES.intersection(rule_matches))
    if decision == "DECLINE":
        return TriageResult(True, "P1" if score >= 0.9 or high_risk else "P2")
    if decision == "REVIEW":
        return TriageResult(True, "P2" if high_risk else "P3")
    if score >= review_threshold:
        return TriageResult(True, "P4")
    return TriageResult(False)
