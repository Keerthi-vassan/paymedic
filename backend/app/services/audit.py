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
    )
    db.add(entry)
    db.commit()
    return entry
