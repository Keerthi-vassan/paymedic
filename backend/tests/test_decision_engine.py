from app.config import settings
from app.services.decision_engine import DECLINE_TYPE, ROOT_CAUSE_ACTIONS, decide


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


def test_network_ceiling_escalates_regardless_of_per_cause_cap():
    decision = decide(
        root_cause="gateway_timeout",
        confidence=0.95,
        risk_score=0.1,
        attempts_so_far=settings.network_retry_ceiling,
    )
    assert decision.escalate is True
    assert "network compliance ceiling" in decision.reasoning


def test_below_network_ceiling_but_at_per_cause_cap_still_uses_retry_cap_reasoning():
    # gateway_timeout's own cap is 3, well under the 15-attempt network
    # ceiling -- proves the new check doesn't preempt the existing
    # per-cause-cap message anywhere below the real ceiling.
    decision = decide(
        root_cause="gateway_timeout",
        confidence=0.95,
        risk_score=0.1,
        attempts_so_far=len(ROOT_CAUSE_ACTIONS["gateway_timeout"]),
    )
    assert decision.escalate is True
    assert "retry cap reached" in decision.reasoning
    assert "network compliance ceiling" not in decision.reasoning


def test_policy_tables_cover_exactly_the_same_root_causes():
    """Three tables key off the same six causes with nothing structurally
    keeping them aligned -- adding a root cause to one and forgetting another
    would silently produce a cause with actions but no success model, or a
    retry policy with no soft/hard classification.
    """
    from app.services.executor import SUCCESS_PROBABILITIES

    assert set(ROOT_CAUSE_ACTIONS) == set(DECLINE_TYPE)
    assert set(ROOT_CAUSE_ACTIONS) == set(SUCCESS_PROBABILITIES)


def test_every_action_sequence_has_a_matching_success_probability():
    """A cause permitted N attempts needs N probabilities: one short, and the
    final attempt would silently always fail regardless of policy.
    """
    from app.services.executor import SUCCESS_PROBABILITIES

    for root_cause, actions in ROOT_CAUSE_ACTIONS.items():
        assert len(SUCCESS_PROBABILITIES[root_cause]) == len(actions), root_cause


def test_hard_declines_are_never_retried_against_the_same_instrument():
    """The soft/hard taxonomy has to be enforced by the action table, not just
    asserted by the label: no hard-decline cause may be assigned a retry.
    """
    from app.services.decision_engine import RETRY_ACTIONS

    for root_cause, actions in ROOT_CAUSE_ACTIONS.items():
        if DECLINE_TYPE[root_cause] == "hard":
            assert not (set(actions) & RETRY_ACTIONS), root_cause


def test_every_cause_stays_under_the_network_compliance_ceiling():
    for root_cause, actions in ROOT_CAUSE_ACTIONS.items():
        assert len(actions) < settings.network_retry_ceiling, root_cause
