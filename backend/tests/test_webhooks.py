import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import UNKNOWN_ROOT_CAUSE, FailedPayment
from app.services import ingest

SECRET = "test_webhook_secret"


def _event(payment_id="pay_LiveTest001", **entity_overrides):
    entity = {
        "id": payment_id,
        "amount": 60600,
        "currency": "INR",
        "status": "failed",
        "method": "card",
        "card_id": "card_ABC123",
        "card": {"id": "card_ABC123", "issuer": "HDFC", "network": "Visa", "last4": "1111"},
        "email": "buyer@example.com",
        "contact": "+919000000000",
        "notes": {"customer_id": "cust_42", "ip_address": "203.0.113.9"},
        "error_code": "BAD_REQUEST_ERROR",
        "error_source": "customer",
        "error_step": "payment_authorization",
        "error_reason": "insufficient_funds",
        "created_at": 1774000000,
    }
    entity.update(entity_overrides)
    return {
        "entity": "event",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {"payment": {"entity": entity}},
        "created_at": 1774000000,
    }


def _signed(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def client(db, monkeypatch):
    monkeypatch.setattr(settings, "razorpay_webhook_secret", SECRET)
    # The router calls create_all on the shared engine; point it at the
    # in-memory session's bind so it never touches the real database file.
    monkeypatch.setattr("app.routers.webhooks.engine", db.get_bind())
    Base.metadata.create_all(bind=db.get_bind())

    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _post(client, event, signature=None, secret=SECRET):
    body = json.dumps(event).encode()
    headers = {
        "X-Razorpay-Signature": signature if signature is not None else _signed(body, secret),
        "Content-Type": "application/json",
    }
    return client.post("/webhooks/razorpay", content=body, headers=headers)


def test_valid_signed_delivery_is_ingested(client, db):
    response = _post(client, _event())

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    row = db.get(FailedPayment, "pay_LiveTest001")
    assert row is not None
    assert row.ingest_source == "razorpay_webhook"
    assert row.status == "open"
    assert row.amount == 60600
    # Razorpay's own error fields map straight across -- the whole reason the
    # synthetic schema mirrors this shape.
    assert row.error_reason == "insufficient_funds"
    assert row.payment_instrument_id == "card_ABC123"
    assert row.issuer_bank == "HDFC"
    assert row.ip_address == "203.0.113.9"
    assert row.customer_id == "cust_42"


def test_real_events_carry_no_ground_truth_or_risk_score(client, db):
    """Both are absent from a real webhook, and must be recorded as absent
    rather than guessed -- these rows are excluded from accuracy metrics and
    can never trip the single-transaction fraud rule.
    """
    _post(client, _event())

    row = db.get(FailedPayment, "pay_LiveTest001")
    assert row.true_root_cause == UNKNOWN_ROOT_CAUSE
    assert row.risk_score == 0.0


def test_bad_signature_is_rejected(client, db):
    response = _post(client, _event(), signature="deadbeef")

    assert response.status_code == 401
    assert db.get(FailedPayment, "pay_LiveTest001") is None


def test_missing_signature_header_is_rejected(client, db):
    body = json.dumps(_event()).encode()
    response = client.post("/webhooks/razorpay", content=body)

    assert response.status_code == 401
    assert db.get(FailedPayment, "pay_LiveTest001") is None


def test_endpoint_refuses_everything_when_no_secret_is_configured(client, db, monkeypatch):
    """Falling open here would mean an unauthenticated path that can insert
    rows into the payment table -- strictly worse than having no endpoint.
    """
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "")

    response = _post(client, _event(), secret="anything")

    assert response.status_code == 503
    assert db.get(FailedPayment, "pay_LiveTest001") is None


def test_redelivery_is_idempotent(client, db):
    first = _post(client, _event())
    second = _post(client, _event())

    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "duplicate"
    assert db.query(FailedPayment).count() == 1


def test_unsupported_event_type_is_rejected(client, db):
    event = _event()
    event["event"] = "payment.captured"

    response = _post(client, event)

    assert response.status_code == 422
    assert db.query(FailedPayment).count() == 0


def test_malformed_payload_is_rejected(client, db):
    event = _event()
    event["payload"] = {}

    response = _post(client, event)

    assert response.status_code == 422
    assert db.query(FailedPayment).count() == 0


def test_upi_payment_uses_the_vpa_as_the_instrument_id():
    """The instrument id is the key the card-testing velocity check groups
    by, so a non-card method must still resolve to something stable.
    """
    row = ingest.to_failed_payment_row(
        _event(payment_id="pay_upi", method="upi", card_id=None, card=None, vpa="buyer@okhdfc")
    )

    assert row["payment_instrument_id"] == "buyer@okhdfc"


def test_missing_optional_fields_do_not_break_ingestion():
    row = ingest.to_failed_payment_row(
        {"event": "payment.failed", "payload": {"payment": {"entity": {"id": "pay_bare"}}}}
    )

    assert row["transaction_id"] == "pay_bare"
    assert row["amount"] == 0
    assert row["ip_address"] == "unknown"
    assert row["error_reason"] is None
