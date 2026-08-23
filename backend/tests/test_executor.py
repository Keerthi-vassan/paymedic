from app.services.executor import SUCCESS_PROBABILITIES, execute, resolution_delay_minutes


def test_outcome_is_deterministic_for_same_transaction_and_attempt():
    outcomes = {execute("txn_abc123", "gateway_timeout", 1) for _ in range(5)}
    assert len(outcomes) == 1


def test_different_transactions_can_get_different_outcomes():
    outcomes = {
        execute(f"txn_{i}", "gateway_timeout", 1) for i in range(50)
    }
    assert outcomes == {"success", "fail"}


def test_out_of_range_attempt_number_fails_safely():
    assert execute("txn_abc123", "gateway_timeout", 0) == "fail"
    assert execute("txn_abc123", "gateway_timeout", 99) == "fail"


def test_possible_fraud_never_succeeds():
    for i in range(20):
        assert execute(f"txn_{i}", "possible_fraud", 1) == "fail"


def test_success_rate_roughly_matches_documented_probability():
    root_cause = "network_drop"
    attempt_number = 1
    expected = SUCCESS_PROBABILITIES[root_cause][attempt_number - 1]

    successes = sum(
        1
        for i in range(500)
        if execute(f"txn_{i}", root_cause, attempt_number) == "success"
    )
    observed_rate = successes / 500

    assert abs(observed_rate - expected) < 0.1


def test_resolution_delay_is_deterministic():
    assert resolution_delay_minutes("retry_with_backoff", 2) == resolution_delay_minutes(
        "retry_with_backoff", 2
    )


def test_retry_immediate_stays_near_instant_at_every_attempt():
    for attempt_number in (1, 2, 3):
        assert resolution_delay_minutes("retry_immediate", attempt_number) <= 5


def test_retry_with_backoff_escalates_across_attempts():
    delay_1 = resolution_delay_minutes("retry_with_backoff", 1)
    delay_2 = resolution_delay_minutes("retry_with_backoff", 2)
    delay_3 = resolution_delay_minutes("retry_with_backoff", 3)
    assert delay_1 < delay_2 < delay_3


def test_unknown_action_or_attempt_falls_back_to_zero():
    assert resolution_delay_minutes("not_a_real_action", 1) == 0
    assert resolution_delay_minutes("retry_with_backoff", 99) == 0
