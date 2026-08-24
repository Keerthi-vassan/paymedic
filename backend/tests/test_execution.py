from datetime import datetime

from app.models import FailedPayment
from app.services import executor
from app.services.execution import attempt_real_execution
from app.services.execution.razorpay_client import RazorpayAPIError


def _make_real_candidate(transaction_id="txn_real_1", amount=15000, root_cause="gateway_timeout"):
    return FailedPayment(
        transaction_id=transaction_id,
        customer_id="cust_1",
        amount=amount,
        currency="INR",
        payment_method="netbanking",
        payment_instrument_id="nb_1",
        issuer_bank="Test Bank",
        ip_address="203.0.113.5",
        error_code="GATEWAY_ERROR",
        error_source="gateway",
        error_step="payment_authorization",
        error_reason="gateway_timeout_error",
        failed_at=datetime.utcnow(),
        network_type="wifi",
        latency_ms=1000,
        risk_score=0.2,
        true_root_cause=root_cause,
        status="open",
        is_real=True,
    )


def test_falls_back_to_simulated_when_order_creation_fails(monkeypatch):
    """The one path that must never break the pipeline: if Razorpay's API
    is unreachable/errors, attempt_real_execution must return the exact
    same outcome the deterministic simulated roll would have, with
    verified=False -- so a broken/unreachable Razorpay account degrades
    that one transaction back to 100% simulated rather than raising.
    """

    def _raise(*args, **kwargs):
        raise RazorpayAPIError("simulated network failure")

    monkeypatch.setattr("app.services.execution.create_order", _raise)

    payment = _make_real_candidate()
    expected_outcome = executor.execute(payment.transaction_id, "gateway_timeout", 1)

    result = attempt_real_execution(payment, "gateway_timeout", 1)

    assert result.outcome == expected_outcome
    assert result.verified is False
    assert result.execution_source == "simulated"
    assert result.gateway_order_id is None
    assert result.gateway_payment_id is None


def test_falls_back_to_simulated_when_browser_automation_fails(monkeypatch):
    """Same fallback guarantee, but for the browser-automation half of the
    flow: order creation succeeds, but drive_netbanking_payment never
    manages to click through (timeout, selector breakage, etc).
    """
    monkeypatch.setattr(
        "app.services.execution.create_order",
        lambda **kwargs: {"id": "order_fake_123"},
    )
    monkeypatch.setattr(
        "app.services.execution.drive_netbanking_payment",
        lambda *args, **kwargs: {"clicked": False, "detail": "simulated automation failure"},
    )

    payment = _make_real_candidate(transaction_id="txn_real_2")
    expected_outcome = executor.execute(payment.transaction_id, "gateway_timeout", 1)

    result = attempt_real_execution(payment, "gateway_timeout", 1)

    assert result.outcome == expected_outcome
    assert result.verified is False
    assert result.execution_source == "simulated"


def test_want_success_target_matches_deterministic_simulated_roll(monkeypatch):
    """The browser is asked to aim for whatever the deterministic hash-roll
    already decided, so seed=42 reproducibility holds even for real
    candidates -- verify the exact want_success value passed through.
    """
    captured = {}

    def _fake_drive(harness_url, want_success, timeout_seconds):
        captured["want_success"] = want_success
        return {"clicked": False, "detail": "not exercising the real API in this test"}

    monkeypatch.setattr("app.services.execution.create_order", lambda **kwargs: {"id": "order_fake_456"})
    monkeypatch.setattr("app.services.execution.drive_netbanking_payment", _fake_drive)

    payment = _make_real_candidate(transaction_id="txn_real_3")
    expected_outcome = executor.execute(payment.transaction_id, "gateway_timeout", 1)

    attempt_real_execution(payment, "gateway_timeout", 1)

    assert captured["want_success"] == (expected_outcome == "success")
