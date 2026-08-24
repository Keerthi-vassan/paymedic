"""Orchestrates a real Razorpay test-mode execution attempt for one bounded
action: create a real order, drive a headless browser through Razorpay's
actual netbanking + mock-bank-page flow, and report what genuinely happened.
Only ever called for the FIRST bounded action of a small, fixed-count subset
of transactions (FailedPayment.is_real) -- see generate_dataset.py's
REAL_CANDIDATE_ROOT_CAUSES for why. Any failure in this module (timeout,
automation breakage, API error) falls back to the same simulated outcome
every other transaction uses, so a broken browser automation never blocks
the pipeline -- it just silently degrades that one transaction back to
100% simulated, exactly as if is_real had been False.
"""

import time
from dataclasses import dataclass

from app.config import settings
from app.models import FailedPayment
from app.services import executor
from app.services.execution.browser_driver import drive_netbanking_payment
from app.services.execution.razorpay_client import RazorpayAPIError, create_order, fetch_order_payments

HARNESS_BASE_URL = "http://localhost:8000/internal/checkout-harness"

_TERMINAL_STATUSES = {"captured", "failed"}


@dataclass
class RealExecutionResult:
    outcome: str  # "success" | "fail" -- always one of these, never "error" (caller sees only the simulated fallback on error)
    verified: bool  # True only if a real Razorpay transaction actually completed
    execution_source: str  # "real_razorpay" | "simulated"
    gateway_order_id: str | None
    gateway_payment_id: str | None
    gateway_status: str | None


def attempt_real_execution(payment: FailedPayment, root_cause: str, attempt_number: int) -> RealExecutionResult:
    # The target outcome is the same deterministic simulated roll every
    # other transaction uses -- keeps seed=42 reproducibility intact even
    # for real candidates, and gives the browser driver a concrete
    # success/fail button to aim for rather than "whatever Razorpay feels
    # like today."
    simulated_outcome = executor.execute(payment.transaction_id, root_cause, attempt_number)
    want_success = simulated_outcome == "success"

    fallback = RealExecutionResult(
        outcome=simulated_outcome,
        verified=False,
        execution_source="simulated",
        gateway_order_id=None,
        gateway_payment_id=None,
        gateway_status=None,
    )

    try:
        order = create_order(amount=payment.amount, receipt=payment.transaction_id)
    except RazorpayAPIError:
        return fallback

    order_id = order["id"]
    harness_url = f"{HARNESS_BASE_URL}?key_id={settings.razorpay_key_id}&order_id={order_id}&amount={payment.amount}"

    click_result = drive_netbanking_payment(
        harness_url,
        want_success=want_success,
        timeout_seconds=settings.razorpay_real_execution_timeout_seconds,
    )
    if not click_result["clicked"]:
        return fallback

    # The browser's job ends at clicking Success/Failure -- Razorpay's own
    # Orders API is polled directly for the actual outcome rather than
    # trusting the checkout widget's client-side JS callback, which proved
    # unreliable under headless automation (confirmed live: a payment was
    # genuinely captured server-side while the callback never fired).
    payment = _poll_for_terminal_payment(order_id, settings.razorpay_real_execution_timeout_seconds)
    if payment is None:
        return fallback

    outcome = "success" if payment["status"] == "captured" else "fail"
    return RealExecutionResult(
        outcome=outcome,
        verified=True,
        execution_source="real_razorpay",
        gateway_order_id=order_id,
        gateway_payment_id=payment.get("id"),
        gateway_status=payment.get("status"),
    )


def _poll_for_terminal_payment(order_id: str, timeout_seconds: int) -> dict | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            payments = fetch_order_payments(order_id)
        except RazorpayAPIError:
            payments = []
        terminal = [p for p in payments if p.get("status") in _TERMINAL_STATUSES]
        if terminal:
            return terminal[-1]
        time.sleep(1.5)
    return None
