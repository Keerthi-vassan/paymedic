from datetime import datetime

import pytest

from app.models import FailedPayment
from app.services import classifier
from app.services.llm.base import LLMClassification


def make_payment(**overrides) -> FailedPayment:
    defaults = dict(
        transaction_id="txn_test",
        customer_id="cust_test",
        amount=100000,
        currency="INR",
        payment_method="card",
        payment_instrument_id="card_test",
        issuer_bank="Test Bank",
        ip_address="203.0.113.1",
        error_code="GATEWAY_ERROR",
        error_source="gateway",
        error_step="payment_authorization",
        error_reason="gateway_timeout_error",
        failed_at=datetime(2026, 1, 1),
        network_type="wifi",
        latency_ms=100,
        risk_score=0.2,
        true_root_cause="gateway_timeout",
        status="open",
        total_attempts=0,
        recovered_amount=0,
    )
    defaults.update(overrides)
    return FailedPayment(**defaults)


def test_known_error_reason_is_classified_deterministically_without_llm():
    payment = make_payment(error_reason="insufficient_funds", risk_score=0.1)
    result = classifier.classify(payment)
    assert result.root_cause == "insufficient_funds"
    assert result.source == "rule_engine"
    assert result.confidence >= 0.9


def test_high_risk_score_is_flagged_as_fraud_regardless_of_error_reason():
    payment = make_payment(error_reason="gateway_timeout_error", risk_score=0.9)
    result = classifier.classify(payment)
    assert result.root_cause == "possible_fraud"
    assert result.source == "rule_engine"


def test_unrecognized_error_reason_routes_to_llm(monkeypatch):
    """With one sample, agreement is trivially 1.0 so confidence collapses to
    the self-reported number -- i.e. exactly the pre-consensus behaviour.
    """
    payment = make_payment(error_reason="some_unknown_reason", risk_score=0.1)
    monkeypatch.setattr(classifier.settings, "classification_samples", 1)

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
    payment = make_payment(error_reason="some_unknown_reason", risk_score=0.1)

    class FailingProvider:
        name = "stub"

        def classify_ambiguous(self, payment):
            raise RuntimeError("provider unreachable")

    monkeypatch.setattr(classifier.llm, "get_provider", lambda: FailingProvider())

    result = classifier.classify(payment)
    assert result.root_cause == "ambiguous"
    assert result.confidence == 0.0
    assert result.source == "llm:stub:error"


class SequenceProvider:
    """Returns a scripted sequence of results (or raises, for Exception
    entries), one per call -- so a test can specify exactly what the model
    'said' on each independent sample.
    """

    name = "stub"

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    def classify_ambiguous(self, payment):
        result = self._results[self.calls]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result


def _sample(root_cause, confidence=0.9):
    return LLMClassification(root_cause=root_cause, confidence=confidence, reasoning="stubbed")


def _consensus(monkeypatch, provider, samples=3):
    monkeypatch.setattr(classifier.settings, "classification_samples", samples)
    monkeypatch.setattr(classifier.llm, "get_provider", lambda: provider)
    return classifier.classify(make_payment(error_reason="some_unknown_reason", risk_score=0.1))


def test_unanimous_samples_keep_the_self_reported_confidence(monkeypatch):
    """Agreement is 1.0, so the more pessimistic signal is the self-report."""
    provider = SequenceProvider(*[_sample("gateway_timeout", 0.9)] * 3)

    result = _consensus(monkeypatch, provider)

    assert provider.calls == 3
    assert result.root_cause == "gateway_timeout"
    assert result.confidence == 0.9
    assert "3/3 samples agreed" in result.reasoning


def test_unanimous_but_hesitant_stays_low(monkeypatch):
    """Consistency alone must not launder a model that says it is unsure."""
    provider = SequenceProvider(*[_sample("gateway_timeout", 0.3)] * 3)

    result = _consensus(monkeypatch, provider)

    assert result.confidence == 0.3  # min(1.0 agreement, 0.3 self-report)


def test_confident_but_inconsistent_is_pulled_down_below_the_gate(monkeypatch):
    """The case self-consistency exists to catch: the model is emphatic every
    time, and says something different every time. Old behaviour would have
    passed the 0.6 gate on a self-reported 0.99; agreement escalates it.
    """
    provider = SequenceProvider(
        _sample("gateway_timeout", 0.99),
        _sample("network_drop", 0.99),
        _sample("card_declined", 0.99),
    )

    result = _consensus(monkeypatch, provider)

    assert result.confidence == pytest.approx(1 / 3, abs=0.001)
    assert result.confidence < classifier.settings.confidence_threshold


def test_majority_wins_and_agreement_caps_the_confidence(monkeypatch):
    provider = SequenceProvider(
        _sample("gateway_timeout", 0.95),
        _sample("gateway_timeout", 0.95),
        _sample("network_drop", 0.95),
    )

    result = _consensus(monkeypatch, provider)

    assert result.root_cause == "gateway_timeout"
    assert result.confidence == pytest.approx(2 / 3, abs=0.001)
    assert "gateway_timeout x2" in result.reasoning


def test_even_split_falls_below_the_gate(monkeypatch):
    """A genuinely torn classifier escalates without needing a tie special-case."""
    provider = SequenceProvider(
        _sample("gateway_timeout"),
        _sample("gateway_timeout"),
        _sample("network_drop"),
        _sample("network_drop"),
    )

    result = _consensus(monkeypatch, provider, samples=4)

    assert result.confidence == 0.5
    assert result.confidence < classifier.settings.confidence_threshold


def test_partial_sample_failure_uses_the_samples_that_succeeded(monkeypatch):
    provider = SequenceProvider(
        _sample("gateway_timeout", 0.9),
        RuntimeError("rate limited"),
        _sample("gateway_timeout", 0.9),
    )

    result = _consensus(monkeypatch, provider)

    assert result.root_cause == "gateway_timeout"
    assert result.source == "llm:stub"
    assert "2/2 samples agreed" in result.reasoning
    assert "1 sample(s) failed and were excluded" in result.reasoning


def test_total_sample_failure_still_fails_closed(monkeypatch):
    provider = SequenceProvider(*[RuntimeError("provider unreachable")] * 3)

    result = _consensus(monkeypatch, provider)

    assert result.root_cause == "ambiguous"
    assert result.confidence == 0.0
    assert result.source == "llm:stub:error"


def test_majority_of_ambiguous_votes_yields_zero_confidence(monkeypatch):
    """validate_classification forces malformed responses to ambiguous/0.0;
    a majority of those must not be laundered into a confident answer by
    agreeing with each other.
    """
    provider = SequenceProvider(
        _sample("ambiguous", 0.0),
        _sample("ambiguous", 0.0),
        _sample("gateway_timeout", 0.9),
    )

    result = _consensus(monkeypatch, provider)

    assert result.root_cause == "ambiguous"
    assert result.confidence == 0.0
