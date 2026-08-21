from app.services.executor import SUCCESS_PROBABILITIES, execute


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
