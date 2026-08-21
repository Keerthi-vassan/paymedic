from datetime import datetime

import pytest

from app.models import FailedPayment
from app.services import classifier
from app.services.llm.base import LLMClassification


def make_payment(**overrides) -> FailedPayment:
    defaults = dict(
        transaction_id="txn_test",
        customer_id="cust_test",
        amount=1000.0,
        currency="INR",
        payment_method="card",
        payment_instrument_id="card_test",
        issuer_bank="Test Bank",
        error_code="GATEWAY_TIMEOUT",
        error_description="Gateway did not respond in time",
        failed_at=datetime(2026, 1, 1),
        network_type="wifi",
        latency_ms=100,
        risk_score=0.2,
        true_root_cause="gateway_timeout",
        status="open",
        total_attempts=0,
        recovered_amount=0.0,
    )
    defaults.update(overrides)
    return FailedPayment(**defaults)


def test_known_error_code_is_classified_deterministically_without_llm():
    payment = make_payment(error_code="INSUFFICIENT_FUNDS", risk_score=0.1)
    result = classifier.classify(payment)
    assert result.root_cause == "insufficient_funds"
    assert result.source == "rule_engine"
    assert result.confidence >= 0.9


def test_high_risk_score_is_flagged_as_fraud_regardless_of_error_code():
    payment = make_payment(error_code="GATEWAY_TIMEOUT", risk_score=0.9)
    result = classifier.classify(payment)
    assert result.root_cause == "possible_fraud"
    assert result.source == "rule_engine"


def test_unrecognized_error_code_routes_to_llm(monkeypatch):
    payment = make_payment(error_code="SOME_UNKNOWN_CODE", risk_score=0.1)

    class StubProvider:
        name = "stub"

        def classify_ambiguous(self, payment):
            return LLMClassification(root_cause="gateway_timeout", confidence=0.8, reasoning="stubbed")

    monkeypatch.setattr(classifier.llm, "get_provider", lambda: StubProvider())

    result = classifier.classify(payment)
    assert result.root_cause == "gateway_timeout"
    assert result.confidence == 0.8
    assert result.source == "llm:stub"


def test_llm_failure_falls_back_to_safe_escalation(monkeypatch):
    payment = make_payment(error_code="SOME_UNKNOWN_CODE", risk_score=0.1)

    class FailingProvider:
        name = "stub"

        def classify_ambiguous(self, payment):
            raise RuntimeError("provider unreachable")

    monkeypatch.setattr(classifier.llm, "get_provider", lambda: FailingProvider())

    result = classifier.classify(payment)
    assert result.root_cause == "ambiguous"
    assert result.confidence == 0.0
    assert result.source == "llm:stub:error"
