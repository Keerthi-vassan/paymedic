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

from app.config import settings
from app.models import FailedPayment
from app.services import (
    audit,
    classifier,
    decision_engine,
    executor,
    notifier,
    retry_scheduler,
    safety_monitor,
)
from app.services import execution as real_execution

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
        # Projected schedule for this attempt, computed once and reused below
        # for both the audit trail and elapsed_minutes, so the two can't
        # drift. None whenever escalating -- there's no action to schedule,
        # mirroring attempt_number's own None-on-escalate below.
        #
        # Two separate concerns: resolution_delay_minutes decides HOW LONG to
        # wait (day-scale spacing between attempts), retry_scheduler decides
        # WHEN that lands (quiet hours, salary-credit alignment). Whatever
        # the scheduler adjusts is appended to the decision's own reasoning,
        # so the audit trail explains the timing as explicitly as it already
        # explains the action.
        if decision.escalate:
            scheduled_at = None
            schedule_reasoning = None
        else:
            base_delay = executor.resolution_delay_minutes(decision.action, attempt_number)
            adjustment = retry_scheduler.schedule(
                target=payment.failed_at + timedelta(minutes=elapsed_minutes + base_delay),
                action=decision.action,
                root_cause=classification.root_cause,
                base_delay_minutes=base_delay,
            )
            scheduled_at = adjustment.scheduled_at
            schedule_reasoning = adjustment.reasoning

        decision_reasoning = decision.reasoning
        if schedule_reasoning:
            decision_reasoning += f" -- {schedule_reasoning}"

        audit.log_event(
            db,
            transaction_id=payment.transaction_id,
            event_type="decision",
            source="decision_engine",
            reasoning=decision_reasoning,
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

        # Only the FIRST bounded action of a small, fixed-count real-candidate
        # subset (FailedPayment.is_real) goes through an actual Razorpay
        # test-mode transaction -- every later retry on that same
        # transaction, and every other transaction, uses the simulated path.
        # A broken/timed-out real attempt falls back to the same simulated
        # outcome transparently (see execution/__init__.py's fallback).
        use_real = settings.razorpay_execution_enabled and payment.is_real and attempt_number == 1
        if use_real:
            real_result = real_execution.attempt_real_execution(payment, classification.root_cause, attempt_number)
            outcome = real_result.outcome
            payment.real_execution_verified = real_result.verified
            payment.gateway_order_id = real_result.gateway_order_id
            payment.gateway_payment_id = real_result.gateway_payment_id
            execution_source = real_result.execution_source
            gateway_status = real_result.gateway_status
        else:
            outcome = executor.execute(payment.transaction_id, classification.root_cause, attempt_number)
            execution_source = "simulated"
            gateway_status = None

        payment.total_attempts = attempt_number
        # Derived from the scheduled time rather than accumulating raw delays,
        # so any adjustment retry_scheduler made is carried into resolved_at
        # instead of the two silently disagreeing about when this landed.
        elapsed_minutes = (scheduled_at - payment.failed_at).total_seconds() / 60

        reasoning = f"executed {decision.action} (attempt {attempt_number})"
        if use_real:
            reasoning += (
                f" -- real Razorpay test-mode transaction ({execution_source}"
                f"{', verified' if payment.real_execution_verified else ', fell back to simulated'})"
            )

        audit.log_event(
            db,
            transaction_id=payment.transaction_id,
            event_type="action_execution",
            source="executor",
            reasoning=reasoning,
            root_cause=classification.root_cause,
            action_taken=decision.action,
            outcome=outcome,
            attempt_number=attempt_number,
            execution_source=execution_source,
            gateway_order_id=payment.gateway_order_id if use_real else None,
            gateway_payment_id=payment.gateway_payment_id if use_real else None,
            gateway_status=gateway_status,
        )

        # Dunning is the other half of recovery: a reminder that no operator
        # can read the text of isn't auditable. Drafted after execution, so
        # the message is recorded only for a reminder that actually went out.
        if decision.action == "send_reminder":
            notification = notifier.draft(
                root_cause=classification.root_cause,
                amount_paise=payment.amount,
            )
            audit.log_event(
                db,
                transaction_id=payment.transaction_id,
                event_type="notification",
                source=notification.source,
                reasoning=notification.reasoning,
                root_cause=classification.root_cause,
                action_taken=decision.action,
                attempt_number=attempt_number,
                notification_body=notification.body,
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


def _summarize(payments: list[FailedPayment]) -> PipelineRunSummary:
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


def run_batch(db: Session, transaction_ids: list[str] | None = None) -> PipelineRunSummary:
    # is_real rows are excluded here and handled only by run_real_batch below
    # -- keeps this batch's documented ~10-14s/100-txn timing true regardless
    # of whether real execution is enabled, instead of an unpredictable ~15-45s
    # pause per real candidate landing at a random point in the loop.
    query = db.query(FailedPayment).filter(FailedPayment.status == "open", FailedPayment.is_real == False)  # noqa: E712
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

    return _summarize(payments)


def run_real_batch(db: Session, transaction_ids: list[str] | None = None) -> PipelineRunSummary:
    """Processes only the small, fixed-count is_real subset, as its own
    explicit step -- deliberately sequential (not the ThreadPoolExecutor
    run_batch uses for classification) since there are only a handful of
    rows and each involves real network + browser-automation I/O, where
    concurrency would only add flakiness for negligible time savings.
    """
    query = db.query(FailedPayment).filter(FailedPayment.status == "open", FailedPayment.is_real == True)  # noqa: E712
    if transaction_ids:
        query = query.filter(FailedPayment.transaction_id.in_(transaction_ids))

    payments = query.all()

    for payment in payments:
        classification = classifier.classify(payment)
        run_transaction(db, payment, classification)

    return _summarize(payments)
