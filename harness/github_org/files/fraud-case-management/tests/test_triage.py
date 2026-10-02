from fraud_cases.triage import TriageResult, triage


def test_decline_with_very_high_score_is_p1():
    assert triage(0.97, "DECLINE", []) == TriageResult(True, "P1")


def test_decline_is_p2_by_default():
    assert triage(0.82, "DECLINE", []) == TriageResult(True, "P2")


def test_high_risk_rule_escalates_a_review():
    assert triage(0.6, "REVIEW", ["CARD_TESTING"]) == TriageResult(True, "P2")
    assert triage(0.6, "REVIEW", ["NEW_DEVICE"]) == TriageResult(True, "P3")


def test_approve_below_threshold_opens_nothing():
    assert triage(0.12, "APPROVE", []) == TriageResult(False)


def test_approve_above_threshold_gets_a_low_priority_look():
    assert triage(0.55, "APPROVE", [], review_threshold=0.5) == TriageResult(True, "P4")
    assert triage(0.55, "APPROVE", [], review_threshold=0.6) == TriageResult(False)
