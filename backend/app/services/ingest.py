"""Maps a real Razorpay `payment.failed` webhook into the same FailedPayment
shape the generator produces, so a live event and a synthetic one go through
one identical pipeline rather than two parallel ones.

This is the piece that makes the system event-driven rather than
batch-only. Everything downstream -- classification, the decision engine,
the stopping rules, the safety monitor, the audit trail -- is unchanged and
unaware of where a row came from.

Two honest gaps, both recorded on the row rather than papered over:

- **No ground truth.** Nobody knows the "correct" root cause of a real
  failure, so `true_root_cause` is UNKNOWN_ROOT_CAUSE and these rows are
  excluded from every accuracy and false-action figure. A live event can be
  processed but not graded.
- **No risk score.** Razorpay's webhook carries no fraud score, so
  `risk_score` is 0.0 and the `risk_score >= 0.85` fraud rule structurally
  cannot fire on a webhook row. The cross-transaction safety monitor still
  applies to them in full, and the decline-code rules still classify them --
  but the single-transaction fraud gate does not, which is worth knowing
  before reading a webhook row's audit trail.
"""

from datetime import datetime, timezone
from typing import Any

from app.models import UNKNOWN_ROOT_CAUSE

SUPPORTED_EVENT = "payment.failed"


class WebhookPayloadError(ValueError):
    """The delivery was authentic but isn't something this system can ingest."""


def _instrument_id(entity: dict[str, Any]) -> str:
    """Whatever identifies the instrument the charge was attempted against.
    This matters more than it looks: it is the key the safety monitor's
    card-testing velocity check groups by, so picking the wrong field here
    would silently disable that check for webhook rows.
    """
    card = entity.get("card") or {}
    for candidate in (entity.get("card_id"), card.get("id"), entity.get("vpa"), entity.get("bank"), entity.get("wallet")):
        if candidate:
            return str(candidate)
    return f"unknown_{entity['id']}"


def to_failed_payment_row(event: dict[str, Any]) -> dict[str, Any]:
    """Raises WebhookPayloadError for anything this system doesn't ingest --
    the caller turns that into a 4xx rather than storing a half-populated row.
    """
    event_name = event.get("event")
    if event_name != SUPPORTED_EVENT:
        raise WebhookPayloadError(
            f"unsupported event {event_name!r} -- only {SUPPORTED_EVENT!r} is ingested"
        )

    entity = ((event.get("payload") or {}).get("payment") or {}).get("entity") or {}
    if not entity.get("id"):
        raise WebhookPayloadError("payload.payment.entity.id missing")

    card = entity.get("card") or {}
    notes = entity.get("notes") or {}

    created_at = entity.get("created_at")
    failed_at = (
        datetime.fromtimestamp(created_at, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(created_at, (int, float))
        # Naive UTC throughout, matching how failed_at is stored everywhere
        # else -- never a tz-aware value in one code path and not another.
        else datetime.utcnow()
    )

    return {
        "transaction_id": entity["id"],
        "customer_id": str(
            notes.get("customer_id") or entity.get("email") or entity.get("contact") or "unknown"
        ),
        # Already paise in Razorpay's own API -- no conversion, which is the
        # entire reason this project stores amounts as integer paise.
        "amount": int(entity.get("amount") or 0),
        "currency": entity.get("currency") or "INR",
        "payment_method": entity.get("method") or "unknown",
        "payment_instrument_id": _instrument_id(entity),
        "issuer_bank": card.get("issuer") or entity.get("bank") or "unknown",
        # Razorpay does not send the payer's IP. Accepted from notes if the
        # merchant chose to attach it, so the IP-velocity check can work on
        # real traffic where that's wired up, and "unknown" otherwise.
        "ip_address": str(notes.get("ip_address") or "unknown"),
        # The one place the synthetic schema pays off: these four fields are
        # copied straight across, because the generator was built to mirror
        # this exact Razorpay error shape rather than inventing its own.
        "error_code": entity.get("error_code") or "unknown",
        "error_source": entity.get("error_source") or "unknown",
        "error_step": entity.get("error_step") or "unknown",
        "error_reason": entity.get("error_reason"),
        "failed_at": failed_at,
        "network_type": card.get("network") or "unknown",
        "latency_ms": 0,
        "risk_score": 0.0,
        "true_root_cause": UNKNOWN_ROOT_CAUSE,
        "ingest_source": "razorpay_webhook",
        "status": "open",
        "total_attempts": 0,
        "recovered_amount": 0,
        "is_real": False,
        "real_execution_verified": False,
    }
