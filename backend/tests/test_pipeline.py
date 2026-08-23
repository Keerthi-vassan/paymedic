from datetime import datetime

from app.models import AuditLog, FailedPayment
from app.services.classifier import ClassificationResult
from app.pipeline import run_transaction


def make_open_payment(db, **overrides):
    defaults = dict(
        transaction_id="txn_pipeline_test",
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
    )
    defaults.update(overrides)
    payment = FailedPayment(**defaults)
    db.add(payment)
    db.commit()
    return payment


def get_first_decision_event(db, transaction_id):
    # Not necessarily the only "decision" event -- a non-escalating first
    # attempt may fail and loop into a second attempt. The first is enough to
    # verify scheduled_at gets populated at decision time.
    return (
        db.query(AuditLog)
        .filter(AuditLog.transaction_id == transaction_id, AuditLog.event_type == "decision")
        .order_by(AuditLog.id)
        .first()
    )


def test_scheduled_at_is_populated_when_not_escalating(db):
    payment = make_open_payment(db, risk_score=0.2, total_attempts=0)
    classification = ClassificationResult(
        root_cause="gateway_timeout", confidence=0.95, reasoning="test", source="rule_engine"
    )

    run_transaction(db, payment, classification)

    decision_event = get_first_decision_event(db, payment.transaction_id)
    assert decision_event.scheduled_at is not None
    assert decision_event.scheduled_at > payment.failed_at


def test_scheduled_at_is_null_when_escalating(db):
    payment = make_open_payment(db, risk_score=0.9, total_attempts=0)
    classification = ClassificationResult(
        root_cause="possible_fraud", confidence=1.0, reasoning="test", source="rule_engine"
    )

    run_transaction(db, payment, classification)

    decision_event = get_first_decision_event(db, payment.transaction_id)
    assert decision_event.scheduled_at is None
    assert payment.status == "escalated"
