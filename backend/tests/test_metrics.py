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
    assert summary.false_action_rate == 50.0  # 1 blocked / 2 actioned (txn 1 and 3)
    assert summary.fraud_block_rate == 100.0  # both fraud cases (3, 4) ended blocked/escalated
    assert summary.avg_time_to_recovery_minutes == 10.0
    assert summary.median_time_to_recovery_minutes == 10.0


def test_summary_handles_empty_batch(db):
    summary = metrics.compute_summary(db)
    assert summary.total_transactions == 0
    assert summary.recovery_rate == 0.0
    assert summary.avg_time_to_recovery_minutes is None
    assert summary.median_time_to_recovery_minutes is None


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
