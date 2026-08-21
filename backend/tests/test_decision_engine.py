from app.config import settings
from app.services.decision_engine import ROOT_CAUSE_ACTIONS, decide


def test_fraud_root_cause_always_escalates_regardless_of_confidence_or_attempts():
    for confidence in (0.0, 0.5, 1.0):
        for attempts in (0, 1, 5):
            decision = decide(
                root_cause="possible_fraud",
                confidence=confidence,
                risk_score=0.1,
                attempts_so_far=attempts,
            )
            assert decision.escalate is True
            assert decision.action is None


def test_high_risk_score_always_escalates_even_for_a_clear_non_fraud_cause():
    decision = decide(
        root_cause="gateway_timeout",
        confidence=0.95,
        risk_score=settings.fraud_risk_score_threshold,
        attempts_so_far=0,
    )
    assert decision.escalate is True
    assert decision.action is None


def test_low_confidence_escalates_instead_of_acting():
    decision = decide(
        root_cause="gateway_timeout",
        confidence=settings.confidence_threshold - 0.01,
        risk_score=0.1,
        attempts_so_far=0,
    )
    assert decision.escalate is True


def test_retry_cap_is_enforced_for_every_root_cause():
    for root_cause, sequence in ROOT_CAUSE_ACTIONS.items():
        max_attempts = len(sequence)
        decision = decide(
            root_cause=root_cause,
            confidence=0.95,
            risk_score=0.1,
            attempts_so_far=max_attempts,
        )
        assert decision.escalate is True, f"{root_cause} did not escalate at its cap"


def test_action_sequence_progresses_through_attempts():
    decision_1 = decide(root_cause="gateway_timeout", confidence=0.95, risk_score=0.1, attempts_so_far=0)
    decision_2 = decide(root_cause="gateway_timeout", confidence=0.95, risk_score=0.1, attempts_so_far=1)

    assert decision_1.action == "retry_immediate"
    assert decision_2.action == "retry_with_backoff"
    assert decision_1.escalate is False
    assert decision_2.escalate is False


def test_possible_fraud_has_zero_max_attempts():
    assert ROOT_CAUSE_ACTIONS["possible_fraud"] == []
