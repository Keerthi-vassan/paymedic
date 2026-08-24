"""Real Razorpay webhook ingestion -- the event-driven entry point.

Until this existed, the only way a transaction entered the system was the
demo's own "Generate Batch" button, i.e. the system only ever saw inputs it
had written itself. This endpoint accepts the actual `payment.failed` event
Razorpay emits, verifies it really came from Razorpay, and puts it into the
same table the generator writes to -- from which the existing pipeline picks
it up with no special-casing anywhere downstream.

Security posture, since this is the one endpoint reachable by an outside
party: every delivery must carry a valid HMAC-SHA256 signature over the raw
request body, compared in constant time. If no webhook secret is configured
the endpoint refuses everything rather than falling open -- an unauthenticated
path that can insert rows into the payment table would be strictly worse than
having no endpoint at all.
"""

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_db
from app.models import FailedPayment
from app.services import ingest
from app.services.ingest import WebhookPayloadError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(raw_body: bytes, provided_signature: str | None) -> None:
    if not settings.razorpay_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Webhook ingestion is not configured -- set RAZORPAY_WEBHOOK_SECRET. "
                "Deliveries are refused rather than accepted unverified."
            ),
        )

    if not provided_signature:
        raise HTTPException(status_code=401, detail="Missing X-Razorpay-Signature header")

    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    # Constant-time: a plain == would leak the correct signature one byte at
    # a time to anyone able to measure response latency across many attempts.
    if not hmac.compare_digest(expected, provided_signature):
        raise HTTPException(status_code=401, detail="Signature verification failed")


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    # The signature covers the exact bytes Razorpay sent, so it must be
    # verified against the raw body before any parsing -- re-serializing a
    # parsed payload would change the bytes and never match.
    raw_body = await request.body()
    _verify_signature(raw_body, x_razorpay_signature)

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Body is not valid JSON: {exc}") from exc

    try:
        row = ingest.to_failed_payment_row(event)
    except WebhookPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    Base.metadata.create_all(bind=engine)

    # Razorpay retries a delivery until it is acknowledged, so the same
    # payment id can legitimately arrive several times. Keyed on the real
    # payment id, which makes redelivery naturally idempotent -- and the
    # response says which happened rather than silently pretending it was new.
    existing = db.get(FailedPayment, row["transaction_id"])
    if existing is not None:
        return {
            "status": "duplicate",
            "transaction_id": row["transaction_id"],
            "detail": "Payment already ingested; redelivery acknowledged, nothing re-inserted.",
        }

    db.add(FailedPayment(**row))
    db.commit()

    return {
        "status": "accepted",
        "transaction_id": row["transaction_id"],
        "detail": (
            "Ingested as an open transaction. It is picked up by the next pipeline run "
            "exactly like a generated row, but is excluded from accuracy metrics -- a real "
            "event carries no ground-truth label."
        ),
    }
