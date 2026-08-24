import pytest

from app.services import notifier


class _StubProvider:
    name = "stub"

    def __init__(self, response):
        self._response = response
        self.calls = 0

    def draft_text(self, system_prompt, user_content, max_tokens):
        self.calls += 1
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


@pytest.fixture(autouse=True)
def _clear_template_cache():
    notifier.reset_cache()
    yield
    notifier.reset_cache()


def _use(monkeypatch, provider):
    monkeypatch.setattr(notifier.settings, "notification_llm_enabled", True)
    monkeypatch.setattr(notifier.llm, "get_provider", lambda: provider)
    return provider


def test_template_used_verbatim_when_llm_disabled(monkeypatch):
    monkeypatch.setattr(notifier.settings, "notification_llm_enabled", False)

    notification = notifier.draft("insufficient_funds", amount_paise=250000)

    assert notification.source == "template"
    assert "₹2,500" in notification.body
    assert "{amount}" not in notification.body


def test_accepted_llm_rewrite_is_used_with_the_amount_substituted(monkeypatch):
    _use(monkeypatch, _StubProvider("We could not take your payment of {amount} just yet."))

    notification = notifier.draft("insufficient_funds", amount_paise=250000)

    assert notification.source == "llm:stub"
    assert notification.body == "We could not take your payment of ₹2,500 just yet."


def test_llm_failure_falls_back_to_the_template(monkeypatch):
    _use(monkeypatch, _StubProvider(RuntimeError("provider unreachable")))

    notification = notifier.draft("insufficient_funds", amount_paise=250000)

    assert notification.source == "template"
    assert "provider unreachable" in notification.reasoning
    assert "₹2,500" in notification.body


@pytest.mark.parametrize(
    "bad_draft, expected_fragment",
    [
        # The failure mode that would actually harm a customer: a fluent model
        # inventing a number nobody supplied.
        ("Pay {amount} within 7 days to avoid a fee.", "digit"),
        ("Call us on 9876543210 about {amount}.", "digit"),
        ("Settle {amount} at http://pay.example/x", "link-like"),
        ("Your payment failed.", "placeholder"),
        ("{amount} and again {amount}", "placeholder"),
        ("", "empty"),
    ],
)
def test_content_guard_rejects_unsafe_drafts(monkeypatch, bad_draft, expected_fragment):
    _use(monkeypatch, _StubProvider(bad_draft))

    notification = notifier.draft("insufficient_funds", amount_paise=250000)

    assert notification.source == "template"
    assert expected_fragment in notification.reasoning
    # Fail-closed: the customer still gets a valid message, never nothing.
    assert "₹2,500" in notification.body


def test_overlong_draft_is_rejected(monkeypatch):
    _use(monkeypatch, _StubProvider("{amount} " + "x" * 500))

    notification = notifier.draft("insufficient_funds", amount_paise=250000)

    assert notification.source == "template"
    assert "over the" in notification.reasoning


def test_template_is_drafted_once_per_root_cause(monkeypatch):
    """A batch must not cost one LLM call per reminder -- the rewrite is
    cached and only the amount varies per transaction.
    """
    provider = _use(monkeypatch, _StubProvider("Your payment of {amount} did not go through."))

    first = notifier.draft("insufficient_funds", amount_paise=250000)
    second = notifier.draft("insufficient_funds", amount_paise=999900)

    assert provider.calls == 1
    assert "₹2,500" in first.body
    assert "₹9,999" in second.body


def test_unknown_root_cause_uses_the_fallback_template(monkeypatch):
    monkeypatch.setattr(notifier.settings, "notification_llm_enabled", False)

    notification = notifier.draft("some_future_cause", amount_paise=100000)

    assert "₹1,000" in notification.body
    assert notification.source == "template"


@pytest.mark.parametrize(
    "paise, expected",
    [
        (100, "₹1"),
        (99900, "₹999"),
        (100000, "₹1,000"),
        (10000000, "₹1,00,000"),
        (109008500, "₹10,90,085"),
    ],
)
def test_amounts_use_indian_digit_grouping(paise, expected):
    assert notifier.format_inr(paise) == expected
