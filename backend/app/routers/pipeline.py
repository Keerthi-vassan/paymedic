from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import pipeline
from app.db import get_db
from app.models import FailedPayment
from app.schemas import PipelineRunRequest, PipelineRunResponse
from app.services import classifier

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResponse)
def run(request: PipelineRunRequest = PipelineRunRequest(), db: Session = Depends(get_db)):
    summary = pipeline.run_batch(db, transaction_ids=request.transaction_ids)
    return PipelineRunResponse(
        processed=summary.processed,
        recovered=summary.recovered,
        escalated=summary.escalated,
        blocked=summary.blocked,
        total_recovered_amount=summary.total_recovered_amount,
    )


@router.post("/run/{transaction_id}", response_model=PipelineRunResponse)
def run_single(transaction_id: str, db: Session = Depends(get_db)):
    payment = db.get(FailedPayment, transaction_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    was_open = payment.status == "open"
    if was_open:
        classification = classifier.classify(payment)
        pipeline.run_transaction(db, payment, classification)

    return PipelineRunResponse(
        processed=1 if was_open else 0,
        recovered=1 if payment.status == "recovered" else 0,
        escalated=1 if payment.status == "escalated" else 0,
        blocked=1 if payment.status == "blocked" else 0,
        total_recovered_amount=payment.recovered_amount if payment.status == "recovered" else 0,
    )
