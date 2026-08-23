"""Cross-transaction checks that run after every action execution. These are
independent of, and run after, the per-transaction classifier and decision
engine -- they exist precisely because a card-testing pattern is invisible to
either of them: each individual transaction can look like an ordinary,
confidently-classified failure while the *pattern* across transactions is
what actually gives it away. This is the mechanism behind the "agent was
wrong, caught itself" case: a transaction can already be marked recovered by
a bounded, individually-reasonable action before one of these checks
retroactively blocks it and its siblings.

Two independent signals are checked, since they catch different (usually
disjoint) attack shapes:
- same payment instrument, many actioned transactions -- one stolen/tested
  card used repeatedly.
- same IP address, many DISTINCT actioned instruments -- a distributed
  card-testing attack (many different stolen cards from one source), which
  the instrument-based check alone cannot see.
"""

from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import FailedPayment
from app.services import audit


def _apply_override(
    db: Session,
    candidates: list[FailedPayment],
    reasoning_fn: Callable[[FailedPayment], str],
) -> bool:
    overridden_any = False
    for p in candidates:
        if p.status == "blocked":
            continue

        p.status = "blocked"
        p.final_action = "safety_override"
        p.recovered_amount = 0
        # A previously-resolved sibling keeps its own resolution timing (still
        # meaningful -- that's genuinely when its own bounded action
        # concluded); only the transaction still mid-processing gets a
        # synthetic "caught quickly" timestamp here.
        if p.resolved_at is None:
            p.resolved_at = p.failed_at + timedelta(minutes=5)

        audit.log_event(
            db,
            transaction_id=p.transaction_id,
            event_type="safety_override",
            source="safety_monitor",
            reasoning=reasoning_fn(p),
        )
        overridden_any = True

    return overridden_any


def _check_instrument_velocity(db: Session, payment: FailedPayment) -> bool:
    window_start = payment.failed_at - timedelta(minutes=settings.velocity_window_minutes)
    window_end = payment.failed_at + timedelta(minutes=settings.velocity_window_minutes)

    related = (
        db.query(FailedPayment)
        .filter(
            FailedPayment.payment_instrument_id == payment.payment_instrument_id,
            FailedPayment.failed_at >= window_start,
            FailedPayment.failed_at <= window_end,
        )
        .all()
    )
    actioned = [p for p in related if p.total_attempts > 0]

    if len(actioned) < settings.velocity_threshold_count:
        return False

    previous_statuses = {p.transaction_id: p.status for p in actioned}
    return _apply_override(
        db,
        actioned,
        reasoning_fn=lambda p: (
            f"{len(actioned)} transactions on this payment instrument within "
            f"{settings.velocity_window_minutes} min -- card-testing pattern detected; "
            f"overriding previous status '{previous_statuses[p.transaction_id]}' and "
            "blocking further automated action on this instrument"
        ),
    )


def _check_ip_velocity(db: Session, payment: FailedPayment) -> bool:
    window_start = payment.failed_at - timedelta(minutes=settings.velocity_window_minutes)
    window_end = payment.failed_at + timedelta(minutes=settings.velocity_window_minutes)

    related = (
        db.query(FailedPayment)
        .filter(
            FailedPayment.ip_address == payment.ip_address,
            FailedPayment.failed_at >= window_start,
            FailedPayment.failed_at <= window_end,
        )
        .all()
    )
    actioned = [p for p in related if p.total_attempts > 0]
    distinct_instruments = {p.payment_instrument_id for p in actioned}

    if len(distinct_instruments) < settings.ip_velocity_threshold_count:
        return False

    previous_statuses = {p.transaction_id: p.status for p in actioned}
    return _apply_override(
        db,
        actioned,
        reasoning_fn=lambda p: (
            f"{len(distinct_instruments)} distinct payment instruments from IP "
            f"{payment.ip_address} within {settings.velocity_window_minutes} min -- "
            f"distributed card-testing pattern detected; overriding previous status "
            f"'{previous_statuses[p.transaction_id]}' and blocking further automated "
            "action from this IP"
        ),
    )


def check_after_action(db: Session, payment: FailedPayment) -> bool:
    """Returns True if either check applied an override to any transaction
    (including possibly `payment` itself). Both checks always run, even if
    the first already changed `payment`'s status -- they match different
    candidate sets, so skipping the second would leave a genuinely distinct
    signal (a different instrument sharing this IP) unevaluated. A row
    matching both checks in the same call is only overridden once: the
    Session's default autoflush means the IP check's query sees the
    instrument check's pending status update, so its own per-row
    "already blocked" guard skips it -- no extra dedup code needed.
    """
    instrument_overridden = _check_instrument_velocity(db, payment)
    ip_overridden = _check_ip_velocity(db, payment)

    overridden_any = instrument_overridden or ip_overridden
    if overridden_any:
        db.commit()

    return overridden_any
