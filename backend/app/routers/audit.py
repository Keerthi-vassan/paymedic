from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog
from app.schemas import AuditListResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
def list_audit(
    transaction_id: str | None = None,
    event_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if transaction_id:
        query = query.filter(AuditLog.transaction_id == transaction_id)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)

    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return AuditListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/{transaction_id}", response_model=AuditListResponse)
def get_transaction_audit(transaction_id: str, db: Session = Depends(get_db)):
    items = (
        db.query(AuditLog)
        .filter(AuditLog.transaction_id == transaction_id)
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    return AuditListResponse(total=len(items), page=1, page_size=len(items) or 1, items=items)
