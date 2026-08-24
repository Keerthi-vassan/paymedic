import random

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import FailedPayment
from app.schemas import FailedPaymentOut, GenerateBatchResponse, PaymentsListResponse
from scripts.generate_dataset import generate_failed_payments

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/generate", response_model=GenerateBatchResponse)
def generate(count: int = 100, seed: int | None = None, db: Session = Depends(get_db)):
    # Dropped rather than only emptied: the batch is regenerated from scratch
    # every time anyway, and recreating the tables means a schema change ships
    # without a migration step or a stale local recovery.db breaking startup.
    # This also clears any webhook-ingested rows, which is the intended
    # semantics of "Generate Batch" -- it resets the whole working set.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Omitting seed gives a genuinely fresh batch each call; passing seed=42
    # explicitly (documented demo path) reproduces the frozen numbers.
    if seed is None:
        seed = random.SystemRandom().randint(0, 2**31 - 1)

    rows = generate_failed_payments(count=count, seed=seed)
    # No explicit row deletion needed -- drop_all above already took both
    # tables with it, including the audit history. That matters because
    # transaction IDs are deterministic per (count, seed), so a fresh batch
    # can reuse an id from a previous run and would otherwise inherit that
    # run's audit trail.
    db.bulk_insert_mappings(FailedPayment, rows)
    db.commit()

    return GenerateBatchResponse(count=len(rows), seed=seed)


@router.get("", response_model=PaymentsListResponse)
def list_payments(
    status: str | None = None,
    root_cause: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(FailedPayment)
    if status:
        query = query.filter(FailedPayment.status == status)
    if root_cause:
        query = query.filter(FailedPayment.true_root_cause == root_cause)

    total = query.count()
    items = (
        query.order_by(FailedPayment.failed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaymentsListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/{transaction_id}", response_model=FailedPaymentOut)
def get_payment(transaction_id: str, db: Session = Depends(get_db)):
    payment = db.get(FailedPayment, transaction_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return payment
