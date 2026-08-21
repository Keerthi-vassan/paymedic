"""Orchestrates classify -> decide -> execute -> log for one transaction at a
time, looping only until the decision engine escalates or the transaction
recovers. Termination is guaranteed by decision_engine's retry cap: attempts
strictly increase each iteration, and every root cause has a finite max
attempts (0 for fraud), so this can never spin.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import FailedPayment
from app.services import audit, classifier, decision_engine, executor, safety_monitor


@dataclass
class PipelineRunSummary:
    processed: int
    recovered: int
    escalated: int
    blocked: int
    total_recovered_amount: float


def run_transaction(db: Session, payment: FailedPayment) -> None:
    if payment.status != "open":
        return

    classification = classifier.classify(payment)
    audit.log_event(
        db,
        transaction_id=payment.transaction_id,
        event_type="classification",
        source=classification.source,
        reasoning=classification.reasoning,
        root_cause=classification.root_cause,
        confidence=classification.confidence,
    )

    while payment.status == "open":
        decision = decision_engine.decide(
            root_cause=classification.root_cause,
            confidence=classification.confidence,
            risk_score=payment.risk_score,
            attempts_so_far=payment.total_attempts,
        )
        audit.log_event(
            db,
            transaction_id=payment.transaction_id,
            event_type="decision",
            source="decision_engine",
            reasoning=decision.reasoning,
            root_cause=classification.root_cause,
            action_taken=decision.action,
            attempt_number=None if decision.escalate else payment.total_attempts + 1,
        )

        if decision.escalate:
            payment.status = "escalated"
            payment.final_action = "escalate_to_human"
            payment.resolved_at = datetime.utcnow()
            db.commit()
            break

        attempt_number = payment.total_attempts + 1
        outcome = executor.execute(payment.transaction_id, classification.root_cause, attempt_number)
        payment.total_attempts = attempt_number

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
            payment.resolved_at = datetime.utcnow()
            db.commit()


def run_batch(db: Session, transaction_ids: list[str] | None = None) -> PipelineRunSummary:
    query = db.query(FailedPayment).filter(FailedPayment.status == "open")
    if transaction_ids:
        query = query.filter(FailedPayment.transaction_id.in_(transaction_ids))

    payments = query.all()
    for payment in payments:
        run_transaction(db, payment)

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
