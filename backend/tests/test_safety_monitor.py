from datetime import datetime, timedelta

from app.models import AuditLog, FailedPayment
from app.services import safety_monitor


def make_actioned_payment(
    db, transaction_id, instrument_id, failed_at, status="recovered", ip_address="203.0.113.10"
):
    payment = FailedPayment(
        transaction_id=transaction_id,
        customer_id="cust_test",
        amount=1000,
        currency="INR",
        payment_method="card",
        payment_instrument_id=instrument_id,
        issuer_bank="Test Bank",
        ip_address=ip_address,
        error_code="GATEWAY_ERROR",
        error_source="gateway",
        error_step="payment_authorization",
        error_reason="gateway_timeout_error",
        failed_at=failed_at,
        network_type="wifi",
        latency_ms=500,
        risk_score=0.4,
        true_root_cause="possible_fraud",
        status=status,
        total_attempts=1,
        recovered_amount=1000 if status == "recovered" else 0,
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


def test_distinct_instruments_sharing_an_ip_trigger_override(db):
    base = datetime(2026, 1, 1, 12, 0, 0)
    shared_ip = "198.51.100.5"
    p1 = make_actioned_payment(db, "txn_1", "card_a", base, ip_address=shared_ip)
    p2 = make_actioned_payment(db, "txn_2", "card_b", base + timedelta(minutes=2), ip_address=shared_ip)
    p3 = make_actioned_payment(db, "txn_3", "card_c", base + timedelta(minutes=4), ip_address=shared_ip)

    triggered = safety_monitor.check_after_action(db, p3)

    assert triggered is True
    for p in (p1, p2, p3):
        assert p.status == "blocked"
        assert p.final_action == "safety_override"


def test_repeated_instrument_on_shared_ip_does_not_count_twice(db):
    # Same IP, 3 rows, but only 2 DISTINCT instruments (card_a used twice) --
    # must not trigger, proving this counts distinct instruments, not rows.
    base = datetime(2026, 1, 1, 12, 0, 0)
    shared_ip = "198.51.100.6"
    p1 = make_actioned_payment(db, "txn_1", "card_a", base, ip_address=shared_ip)
    p2 = make_actioned_payment(db, "txn_2", "card_a", base + timedelta(minutes=2), ip_address=shared_ip)
    p3 = make_actioned_payment(db, "txn_3", "card_b", base + timedelta(minutes=4), ip_address=shared_ip)

    triggered = safety_monitor.check_after_action(db, p3)

    assert triggered is False
    assert p1.status == "recovered"
    assert p2.status == "recovered"
    assert p3.status == "recovered"


def test_transaction_matching_both_patterns_is_overridden_only_once(db):
    # txn_3 matches the instrument check (3 actioned rows on card_shared) AND
    # the IP check (3 distinct instruments -- card_shared/card_d/card_e --
    # share shared_ip) simultaneously. The autoflush-based guard in
    # _apply_override must prevent a duplicate safety_override audit row.
    base = datetime(2026, 1, 1, 12, 0, 0)
    shared_ip = "198.51.100.7"
    p1 = make_actioned_payment(db, "txn_1", "card_shared", base, ip_address=shared_ip)
    p2 = make_actioned_payment(db, "txn_2", "card_shared", base + timedelta(minutes=2), ip_address=shared_ip)
    p3 = make_actioned_payment(db, "txn_3", "card_shared", base + timedelta(minutes=4), ip_address=shared_ip)
    make_actioned_payment(db, "txn_4", "card_d", base + timedelta(minutes=1), ip_address=shared_ip)
    make_actioned_payment(db, "txn_5", "card_e", base + timedelta(minutes=3), ip_address=shared_ip)

    safety_monitor.check_after_action(db, p3)

    overrides = (
        db.query(AuditLog)
        .filter(AuditLog.transaction_id == "txn_3", AuditLog.event_type == "safety_override")
        .all()
    )
    assert len(overrides) == 1
