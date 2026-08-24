from datetime import datetime, timedelta

from app.models import FailedPayment
from app.services import metrics


def make_payment(db, **overrides):
    defaults = dict(
        transaction_id=f"txn_{overrides.get('transaction_id', 'x')}",
        customer_id="cust_test",
        amount=100000,
        currency="INR",
        payment_method="card",
        payment_instrument_id="card_test",
        issuer_bank="Test Bank",
        ip_address="203.0.113.1",
        error_code="GATEWAY_ERROR",
        error_source="gateway",
        error_step="payment_authorization",
        error_reason="gateway_timeout_error",
        failed_at=datetime(2026, 1, 1, 12, 0, 0),
        network_type="wifi",
        latency_ms=500,
        risk_score=0.2,
        true_root_cause="gateway_timeout",
        status="open",
        total_attempts=0,
        recovered_amount=0,
        resolved_at=None,
    )
    defaults.update(overrides)
    payment = FailedPayment(**defaults)
    db.add(payment)
    db.commit()
    return payment


def test_summary_computes_rates_correctly(db):
    make_payment(
        db, transaction_id="1", amount=100.0, status="recovered",
        total_attempts=1, recovered_amount=100.0,
        failed_at=datetime(2026, 1, 1, 12, 0, 0),
        resolved_at=datetime(2026, 1, 1, 12, 10, 0),
    )
    make_payment(db, transaction_id="2", amount=200.0, status="escalated", total_attempts=0)
    make_payment(
        db, transaction_id="3", amount=50.0, status="blocked",
        total_attempts=1, recovered_amount=0.0, true_root_cause="possible_fraud",
    )
    make_payment(
        db, transaction_id="4", amount=300.0, status="escalated",
        total_attempts=0, true_root_cause="possible_fraud",
    )

    summary = metrics.compute_summary(db)

    assert summary.total_transactions == 4
    assert summary.total_at_risk_amount == 650.0
    assert summary.total_recovered_amount == 100.0
    assert summary.recovery_rate == 25.0  # 1/4
    assert summary.escalation_rate == 50.0  # 2/4
    assert summary.blocked_rate == 25.0  # 1/4
    # Two distinct measurements that happen to coincide on this fixture:
    # txn 3 is a true fraud case that got actioned (a real false action), and
    # it is also the one blocked row among the two actioned ones.
    assert summary.false_action_rate == 50.0  # 1 false action / 2 gradeable actioned
    assert summary.false_action_count == 1
    assert summary.safety_override_rate == 50.0  # 1 blocked / 2 actioned
    assert summary.fraud_block_rate == 100.0  # both fraud cases (3, 4) ended blocked/escalated
    assert summary.avg_time_to_recovery_minutes == 10.0
    assert summary.median_time_to_recovery_minutes == 10.0


def test_summary_handles_empty_batch(db):
    summary = metrics.compute_summary(db)
    assert summary.total_transactions == 0
    assert summary.recovery_rate == 0.0
    assert summary.avg_time_to_recovery_minutes is None
    assert summary.median_time_to_recovery_minutes is None
    assert summary.real_candidate_count == 0
    assert summary.real_execution_verified_count == 0


def test_summary_counts_real_execution_candidates(db):
    make_payment(db, transaction_id="1", is_real=True, real_execution_verified=True)
    make_payment(db, transaction_id="2", is_real=True, real_execution_verified=False)
    make_payment(db, transaction_id="3", is_real=False)

    summary = metrics.compute_summary(db)

    assert summary.real_candidate_count == 2
    assert summary.real_execution_verified_count == 1


def test_root_cause_breakdown_groups_correctly(db):
    make_payment(db, transaction_id="1", true_root_cause="gateway_timeout", status="recovered", recovered_amount=100.0)
    make_payment(db, transaction_id="2", true_root_cause="gateway_timeout", status="escalated")
    make_payment(db, transaction_id="3", true_root_cause="card_declined", status="recovered", recovered_amount=50.0)

    rows = {r.root_cause: r for r in metrics.compute_root_cause_breakdown(db)}

    assert rows["gateway_timeout"].total == 2
    assert rows["gateway_timeout"].recovered == 1
    assert rows["gateway_timeout"].escalated == 1
    assert rows["gateway_timeout"].recovery_rate == 50.0
    assert rows["card_declined"].total == 1
    assert rows["card_declined"].recovery_rate == 100.0


def test_timeline_is_cumulative_and_ordered(db):
    make_payment(
        db, transaction_id="1", status="recovered", recovered_amount=100.0,
        resolved_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    make_payment(
        db, transaction_id="2", status="recovered", recovered_amount=50.0,
        resolved_at=datetime(2026, 1, 1, 11, 0, 0),
    )
    make_payment(db, transaction_id="3", status="escalated")

    points = metrics.compute_timeline(db)

    assert len(points) == 2
    assert points[0].cumulative_recovered_amount == 50.0
    assert points[1].cumulative_recovered_amount == 150.0


def make_classification(db, payment, predicted, confidence, source="rule_engine"):
    from app.services import audit

    return audit.log_event(
        db,
        transaction_id=payment.transaction_id,
        event_type="classification",
        source=source,
        reasoning="test",
        root_cause=predicted,
        confidence=confidence,
    )


def test_false_action_rate_counts_misses_the_safety_monitor_never_caught(db):
    """The point of grading against ground truth: a wrong action that nothing
    downstream noticed must still count. Here a true fraud case was actioned
    and ended 'recovered' -- the old blocked/actioned ratio would score this
    batch a perfect 0%.
    """
    from app.services import audit

    p = make_payment(
        db, transaction_id="1", true_root_cause="possible_fraud",
        status="recovered", total_attempts=1, recovered_amount=100000,
    )
    audit.log_event(
        db, transaction_id=p.transaction_id, event_type="action_execution",
        source="executor", reasoning="test", action_taken="retry_immediate",
        outcome="success", attempt_number=1,
    )

    summary = metrics.compute_summary(db)

    assert summary.false_action_count == 1
    assert summary.false_action_rate == 100.0
    assert summary.safety_override_rate == 0.0  # nothing was ever blocked


def test_retrying_a_true_hard_decline_is_a_false_action(db):
    """A card_declined mislabelled as retryable, then retried against the same
    instrument -- the exact combination card networks fine merchants for.
    """
    from app.services import audit

    p = make_payment(
        db, transaction_id="1", true_root_cause="card_declined",
        status="escalated", total_attempts=1,
    )
    audit.log_event(
        db, transaction_id=p.transaction_id, event_type="action_execution",
        source="executor", reasoning="test", action_taken="retry_with_backoff",
        outcome="fail", attempt_number=1,
    )

    assert metrics.compute_summary(db).false_action_count == 1


def test_redirecting_a_hard_decline_is_not_a_false_action(db):
    """suggest_alternate_method sends the customer to a different instrument
    rather than re-hitting the declined one, so it must not be penalised.
    """
    from app.services import audit

    p = make_payment(
        db, transaction_id="1", true_root_cause="card_declined",
        status="escalated", total_attempts=1,
    )
    audit.log_event(
        db, transaction_id=p.transaction_id, event_type="action_execution",
        source="executor", reasoning="test", action_taken="suggest_alternate_method",
        outcome="fail", attempt_number=1,
    )

    assert metrics.compute_summary(db).false_action_count == 0


def test_webhook_rows_are_excluded_from_false_action_grading(db):
    from app.models import UNKNOWN_ROOT_CAUSE

    make_payment(
        db, transaction_id="1", true_root_cause=UNKNOWN_ROOT_CAUSE,
        ingest_source="razorpay_webhook", status="recovered",
        total_attempts=1, recovered_amount=100000,
    )

    summary = metrics.compute_summary(db)

    # No ground truth means no verdict either way -- not a pass, not a fail.
    assert summary.false_action_count == 0
    assert summary.false_action_rate == 0.0


def test_classifier_accuracy_splits_by_path(db):
    p1 = make_payment(db, transaction_id="1", true_root_cause="gateway_timeout")
    p2 = make_payment(db, transaction_id="2", true_root_cause="card_declined")
    p3 = make_payment(db, transaction_id="3", true_root_cause="auth_failure")

    make_classification(db, p1, "gateway_timeout", 0.95)
    make_classification(db, p2, "card_declined", 0.8, source="llm:anthropic")
    make_classification(db, p3, "network_drop", 0.7, source="llm:anthropic")

    result = metrics.compute_classifier_metrics(db)
    paths = {row.path: row for row in result.paths}

    assert result.graded == 3
    assert result.overall_accuracy == 66.67
    assert paths["rule_engine"].total == 1
    assert paths["rule_engine"].accuracy == 100.0
    assert paths["llm"].total == 2
    assert paths["llm"].accuracy == 50.0


def test_failed_llm_calls_are_reported_as_their_own_path(db):
    """A forced-ambiguous classification is not a wrong answer in the same
    sense as a confident miss -- it escalates safely, and lumping it into the
    LLM path would understate that path's real accuracy.
    """
    p = make_payment(db, transaction_id="1", true_root_cause="gateway_timeout")
    make_classification(db, p, "ambiguous", 0.0, source="llm:anthropic:error")

    result = metrics.compute_classifier_metrics(db)
    paths = {row.path: row for row in result.paths}

    assert paths["llm_error"].total == 1
    assert paths["llm"].total == 0


def test_confusion_matrix_surfaces_systematic_misses(db):
    """The card-testing cluster's signature: true fraud confidently read as
    an ordinary gateway timeout.
    """
    for i in range(3):
        p = make_payment(db, transaction_id=str(i), true_root_cause="possible_fraud")
        make_classification(db, p, "gateway_timeout", 0.95)

    result = metrics.compute_classifier_metrics(db)
    row = next(r for r in result.confusion if r.true_root_cause == "possible_fraud")

    assert row.total == 3
    assert row.predicted == {"gateway_timeout": 3}


def test_calibration_reports_accuracy_either_side_of_the_gate(db):
    """The question the system cannot answer about itself: when it says it is
    confident, is it right? Here it is confidently wrong twice and correct
    only below the gate -- so the gate is actively counterproductive.
    """
    for i in range(2):
        p = make_payment(db, transaction_id=f"hi{i}", true_root_cause="card_declined")
        make_classification(db, p, "gateway_timeout", 0.9, source="llm:anthropic")

    p = make_payment(db, transaction_id="lo", true_root_cause="card_declined")
    make_classification(db, p, "card_declined", 0.3, source="llm:anthropic")

    result = metrics.compute_classifier_metrics(db)

    assert result.above_threshold_total == 2
    assert result.above_threshold_accuracy == 0.0
    assert result.below_threshold_total == 1
    assert result.below_threshold_accuracy == 100.0

    buckets = {b.label: b for b in result.calibration}
    assert buckets["0.8-1.0"].total == 2
    assert buckets["0.8-1.0"].accuracy == 0.0
    assert buckets["0.2-0.4"].total == 1
    # Every bucket is always present, so the table's shape is stable.
    assert len(result.calibration) == metrics.CALIBRATION_BUCKET_COUNT


def test_classifier_metrics_exclude_ungraded_webhook_rows(db):
    from app.models import UNKNOWN_ROOT_CAUSE

    p1 = make_payment(db, transaction_id="1", true_root_cause="gateway_timeout")
    p2 = make_payment(
        db, transaction_id="2", true_root_cause=UNKNOWN_ROOT_CAUSE,
        ingest_source="razorpay_webhook",
    )
    make_classification(db, p1, "gateway_timeout", 0.95)
    make_classification(db, p2, "insufficient_funds", 0.95)

    result = metrics.compute_classifier_metrics(db)

    assert result.total_classified == 2
    assert result.graded == 1
    assert result.ungraded == 1
    assert result.overall_accuracy == 100.0


def test_classifier_metrics_handle_an_empty_batch(db):
    result = metrics.compute_classifier_metrics(db)

    assert result.total_classified == 0
    assert result.overall_accuracy == 0.0
    assert result.confusion == []
    assert len(result.calibration) == metrics.CALIBRATION_BUCKET_COUNT
