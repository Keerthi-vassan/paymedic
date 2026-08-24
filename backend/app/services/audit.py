from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_event(
    db: Session,
    transaction_id: str,
    event_type: str,
    source: str,
    reasoning: str,
    root_cause: str | None = None,
    confidence: float | None = None,
    action_taken: str | None = None,
    outcome: str | None = None,
    attempt_number: int | None = None,
    scheduled_at: datetime | None = None,
    execution_source: str | None = None,
    gateway_order_id: str | None = None,
    gateway_payment_id: str | None = None,
    gateway_status: str | None = None,
    notification_body: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        transaction_id=transaction_id,
        event_type=event_type,
        source=source,
        root_cause=root_cause,
        confidence=confidence,
        action_taken=action_taken,
        reasoning=reasoning,
        outcome=outcome,
        attempt_number=attempt_number,
        scheduled_at=scheduled_at,
        execution_source=execution_source,
        gateway_order_id=gateway_order_id,
        gateway_payment_id=gateway_payment_id,
        gateway_status=gateway_status,
        notification_body=notification_body,
    )
    db.add(entry)
    db.commit()
    return entry
