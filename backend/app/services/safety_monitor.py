"""Cross-transaction check that runs after every action execution. This is
independent of, and runs after, the per-transaction classifier and decision
engine -- it exists precisely because a card-testing pattern is invisible to
either of them: each individual transaction can look like an ordinary,
confidently-classified failure while the *pattern* across transactions on the
same payment instrument is what actually gives it away. This is the
mechanism behind the "agent was wrong, caught itself" case: a transaction can
already be marked recovered by a bounded, individually-reasonable action
before this check retroactively blocks it and its siblings.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import FailedPayment
from app.services import audit


def check_after_action(db: Session, payment: FailedPayment) -> bool:
    """Returns True if an override was applied to any transaction in this
    instrument's cluster (including possibly `payment` itself).
    """
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

    overridden_any = False
    for p in actioned:
        if p.status == "blocked":
            continue

        previous_status = p.status
        p.status = "blocked"
        p.final_action = "safety_override"
        p.recovered_amount = 0.0
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
            reasoning=(
                f"{len(actioned)} transactions on this payment instrument within "
                f"{settings.velocity_window_minutes} min -- card-testing pattern detected; "
                f"overriding previous status '{previous_status}' and blocking further "
                "automated action on this instrument"
            ),
        )
        overridden_any = True

    if overridden_any:
        db.commit()

    return overridden_any
