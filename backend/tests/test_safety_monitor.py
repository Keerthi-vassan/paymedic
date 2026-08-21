from datetime import datetime, timedelta

from app.models import FailedPayment
from app.services import safety_monitor


def make_actioned_payment(db, transaction_id, instrument_id, failed_at, status="recovered"):
    payment = FailedPayment(
        transaction_id=transaction_id,
        customer_id="cust_test",
        amount=10.0,
        currency="INR",
        payment_method="card",
        payment_instrument_id=instrument_id,
        issuer_bank="Test Bank",
        error_code="GATEWAY_TIMEOUT",
        error_description="Gateway did not respond in time",
        failed_at=failed_at,
        network_type="wifi",
        latency_ms=500,
        risk_score=0.4,
        true_root_cause="possible_fraud",
        status=status,
        total_attempts=1,
        recovered_amount=10.0 if status == "recovered" else 0.0,
    )
    db.add(payment)
    db.commit()
    return payment


def test_below_threshold_does_not_trigger_override(db):
    base = datetime(2026, 1, 1, 12, 0, 0)
    p1 = make_actioned_payment(db, "txn_1", "card_shared", base)
    p2 = make_actioned_payment(db, "txn_2", "card_shared", base + timedelta(minutes=2))

    triggered = safety_monitor.check_after_action(db, p2)

    assert triggered is False
    assert p1.status == "recovered"
    assert p2.status == "recovered"


def test_velocity_pattern_retroactively_blocks_all_siblings(db):
    base = datetime(2026, 1, 1, 12, 0, 0)
    p1 = make_actioned_payment(db, "txn_1", "card_shared", base)
    p2 = make_actioned_payment(db, "txn_2", "card_shared", base + timedelta(minutes=2))
    p3 = make_actioned_payment(db, "txn_3", "card_shared", base + timedelta(minutes=4))

    triggered = safety_monitor.check_after_action(db, p3)

    assert triggered is True
    for p in (p1, p2, p3):
        assert p.status == "blocked"
        assert p.final_action == "safety_override"
        assert p.recovered_amount == 0.0


def test_unrelated_instrument_is_not_affected(db):
    base = datetime(2026, 1, 1, 12, 0, 0)
    make_actioned_payment(db, "txn_1", "card_shared", base)
    make_actioned_payment(db, "txn_2", "card_shared", base + timedelta(minutes=2))
    other = make_actioned_payment(db, "txn_other", "card_unrelated", base)
    p3 = make_actioned_payment(db, "txn_3", "card_shared", base + timedelta(minutes=4))

    safety_monitor.check_after_action(db, p3)

    assert other.status == "recovered"


def test_outside_time_window_does_not_count_toward_threshold(db):
    base = datetime(2026, 1, 1, 12, 0, 0)
    p1 = make_actioned_payment(db, "txn_1", "card_shared", base)
    p2 = make_actioned_payment(db, "txn_2", "card_shared", base + timedelta(minutes=2))
    p3 = make_actioned_payment(db, "txn_3", "card_shared", base + timedelta(hours=5))

    triggered = safety_monitor.check_after_action(db, p3)

    assert triggered is False
    assert p1.status == "recovered"
    assert p2.status == "recovered"
    assert p3.status == "recovered"


def test_already_blocked_transaction_is_not_reprocessed(db):
    base = datetime(2026, 1, 1, 12, 0, 0)
    p1 = make_actioned_payment(db, "txn_1", "card_shared", base, status="blocked")
    p2 = make_actioned_payment(db, "txn_2", "card_shared", base + timedelta(minutes=2))
    p3 = make_actioned_payment(db, "txn_3", "card_shared", base + timedelta(minutes=4))

    triggered = safety_monitor.check_after_action(db, p3)

    assert triggered is True
    assert p1.status == "blocked"
    assert p2.status == "blocked"
    assert p3.status == "blocked"
