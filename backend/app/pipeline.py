"""Orchestrates classify -> decide -> execute -> log for one transaction at a
time, looping only until the decision engine escalates or the transaction
recovers. Termination is guaranteed by decision_engine's retry cap: attempts
strictly increase each iteration, and every root cause has a finite max
attempts (0 for fraud), so this can never spin.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import FailedPayment
from app.services import audit, classifier, decision_engine, executor, safety_monitor

CLASSIFICATION_WORKERS = 8


@dataclass
class PipelineRunSummary:
    processed: int
    recovered: int
    escalated: int
    blocked: int
    total_recovered_amount: int  # paise


def run_transaction(
    db: Session, payment: FailedPayment, classification: classifier.ClassificationResult
) -> None:
    if payment.status != "open":
        return

    audit.log_event(
        db,
        transaction_id=payment.transaction_id,
        event_type="classification",
        source=classification.source,
        reasoning=classification.reasoning,
        root_cause=classification.root_cause,
        confidence=classification.confidence,
    )

    # Simulated minutes elapsed since failed_at, accumulated as bounded actions
    # are taken -- used to derive a meaningful resolved_at instead of real
    # wall-clock time, since failed_at itself is a backdated synthetic
    # timestamp (see executor.resolution_delay_minutes).
    elapsed_minutes = 0.0

    while payment.status == "open":
        decision = decision_engine.decide(
            root_cause=classification.root_cause,
            confidence=classification.confidence,
            risk_score=payment.risk_score,
            attempts_so_far=payment.total_attempts,
        )
        attempt_number = payment.total_attempts + 1
        # Projected delay/schedule for this attempt, computed once and reused
        # below for both the audit trail and elapsed_minutes, so the two
        # can't drift. None whenever escalating -- there's no action to
        # schedule, mirroring attempt_number's own None-on-escalate below.
        projected_delay = (
            None
            if decision.escalate
            else executor.resolution_delay_minutes(decision.action, attempt_number)
        )
        scheduled_at = (
            None
            if decision.escalate
            else payment.failed_at + timedelta(minutes=elapsed_minutes + projected_delay)
        )
        audit.log_event(
            db,
            transaction_id=payment.transaction_id,
            event_type="decision",
            source="decision_engine",
            reasoning=decision.reasoning,
            root_cause=classification.root_cause,
            action_taken=decision.action,
            attempt_number=None if decision.escalate else attempt_number,
            # Set once, here, and never retroactively updated -- if a later
            # safety_override supersedes this transaction, this stays an
            # honest historical snapshot of what was intended at decision
            # time (mirrors the "previously-resolved sibling keeps its own
            # resolution timing" rule in safety_monitor.py).
            scheduled_at=scheduled_at,
        )

        if decision.escalate:
            payment.status = "escalated"
            payment.final_action = "escalate_to_human"
            payment.resolved_at = payment.failed_at + timedelta(minutes=elapsed_minutes)
            db.commit()
            break

        outcome = executor.execute(payment.transaction_id, classification.root_cause, attempt_number)
        payment.total_attempts = attempt_number
        elapsed_minutes += projected_delay

        audit.log_event(
            db,
            transaction_id=payment.transaction_id,
            event_type="action_execution",
            source="executor",
            reasoning=f"executed {decision.action} (attempt {attempt_number})",
            root_cause=classification.root_cause,
            action_taken=decision.action,
            outcome=outcome,
            attempt_number=attempt_number,
        )

        db.commit()

        # Cross-transaction check, independent of this transaction's own
        # outcome: may retroactively block this transaction (and siblings on
        # the same instrument) even after a bounded, individually-reasonable
        # action was just taken.
        safety_monitor.check_after_action(db, payment)
        if payment.status != "open":
            break

        if outcome == "success":
            payment.status = "recovered"
            payment.final_action = decision.action
            payment.recovered_amount = payment.amount
            payment.resolved_at = payment.failed_at + timedelta(minutes=elapsed_minutes)
            db.commit()


def run_batch(db: Session, transaction_ids: list[str] | None = None) -> PipelineRunSummary:
    query = db.query(FailedPayment).filter(FailedPayment.status == "open")
    if transaction_ids:
        query = query.filter(FailedPayment.transaction_id.in_(transaction_ids))

    payments = query.all()

    # classify() is a pure function of each payment's own fields -- no DB
    # access, no cross-transaction state -- so it's safe to run concurrently.
    # This is where nearly all the wall-clock time goes for ambiguous rows
    # that fall through to the LLM. Everything after this (decide/execute/
    # safety-monitor) stays strictly sequential: the safety monitor's
    # card-testing check depends on transactions being processed in order.
    with ThreadPoolExecutor(max_workers=CLASSIFICATION_WORKERS) as pool:
        classifications = dict(zip(payments, pool.map(classifier.classify, payments)))

    for payment in payments:
        run_transaction(db, payment, classifications[payment])

    recovered = [p for p in payments if p.status == "recovered"]
    escalated = [p for p in payments if p.status == "escalated"]
    blocked = [p for p in payments if p.status == "blocked"]

    return PipelineRunSummary(
        processed=len(payments),
        recovered=len(recovered),
        escalated=len(escalated),
        blocked=len(blocked),
        total_recovered_amount=sum(p.recovered_amount for p in recovered),
    )
