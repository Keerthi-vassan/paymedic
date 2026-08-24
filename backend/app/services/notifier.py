"""Drafts the customer-facing message behind a `send_reminder` action.

Retrying a charge is only half of what a real recovery system does -- the
other half is dunning: telling the customer their payment failed and what
happens next. `send_reminder` was previously a label with no content, which
mattered because it is the first action on `insufficient_funds`, the single
largest failure bucket. An operator reading the audit trail could see that a
reminder was "sent" but never what it actually said.

This is the second place an LLM is used in the system, and it is bounded far
more tightly than the classifier is, because the output is read by a
customer rather than by a rule engine:

- **A template is always produced first**, and is a complete, sendable
  message on its own.
- The LLM is only ever asked to *rewrite that template*, never to originate
  a message, decide whether to send one, or choose an action.
- **It rewrites the template, not the message.** The `{amount}` placeholder
  is left in place and substituted afterwards, so the model never sees or
  emits a real customer's amount, one rewrite serves the whole batch, and
  the guard below can simply reject *every* digit -- a far stronger rule
  than trying to decide which numbers were legitimate.
- **Every rewrite passes a hard guard** (`_rejection_reason`) before use:
  the placeholder must survive intact and exactly once, no digits, no
  links, within the length budget. This is what stops a fluent model from
  inventing a deadline, a discount, a fee, or a support phone number --
  the realistic failure mode for generated payment copy, and the one that
  would actually harm a customer.
- **Failure is always closed**: an LLM error, an empty response, or any
  guard violation falls back to the built-in template verbatim and records
  why in the audit trail. There is no path where a rejected rewrite is sent
  anyway, and none where a customer receives nothing because generation
  failed.

Nothing here can change what action was taken, whether money moved, or how a
transaction was classified -- by the time this runs, the decision engine has
already committed to `send_reminder`.
"""

import re
from dataclasses import dataclass

from app.config import settings
from app.services import llm

SYSTEM_PROMPT = (
    "You rewrite a payment-failure notification template for an Indian customer. Rewrite it so "
    "it reads naturally and politely. Rules, all mandatory: keep every fact identical; keep the "
    "literal placeholder {amount} exactly once, unchanged, braces included; do NOT write any "
    "digit, amount, date, deadline, percentage, fee, discount, phone number, or link; do not "
    "promise anything the template does not promise; do not apologise excessively; plain text "
    "only, no markdown, no subject line, no signature. Reply with the rewritten template and "
    "nothing else."
)

# One template per root cause that can reach send_reminder. Only
# insufficient_funds does today (decision_engine.ROOT_CAUSE_ACTIONS), but the
# fallback keeps this module correct if that policy widens later.
TEMPLATES: dict[str, str] = {
    "insufficient_funds": (
        "Your payment of {amount} could not be completed because your bank reported "
        "insufficient funds. Nothing is owed yet and no charge was made. We will "
        "automatically try again in a few days, or you can complete it yourself any time "
        "from your account."
    ),
}

FALLBACK_TEMPLATE = (
    "Your payment of {amount} could not be completed. No charge was made. We will follow up "
    "shortly, or you can complete it yourself any time from your account."
)

PLACEHOLDER = "{amount}"
_ANY_DIGIT = re.compile(r"\d")
_LINK_MARKERS = ("http", "www.", "://", ".com", ".in/")

# One rewrite serves every transaction sharing a root cause, so a 100-row
# batch costs at most one LLM call per cause rather than one per reminder --
# which is what keeps the sequential half of the pipeline fast. Cleared by
# reset_cache() in tests.
_TEMPLATE_CACHE: dict[str, "DraftedTemplate"] = {}


@dataclass
class DraftedTemplate:
    template: str
    source: str  # template | llm:<provider>
    reasoning: str


@dataclass
class Notification:
    body: str
    source: str
    # Why the final body is the one it is -- always populated, including on
    # the happy path, so the audit trail explains the guard's decision rather
    # than only its failures.
    reasoning: str


def reset_cache() -> None:
    _TEMPLATE_CACHE.clear()


def format_inr(amount_paise: int) -> str:
    """Indian digit grouping (lakh/crore), matching how every amount is shown
    in the dashboard -- a customer-facing message must not be the one place
    that renders 1090085 as 1,090,085.
    """
    rupees = amount_paise // 100
    digits = str(rupees)
    if len(digits) <= 3:
        return f"₹{digits}"

    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return f"₹{','.join(parts)},{tail}"


def _rejection_reason(candidate: str, budget: int) -> str | None:
    """Returns None if the rewritten template is safe to use, else why not."""
    stripped = candidate.strip()
    if not stripped:
        return "empty draft"

    if stripped.count(PLACEHOLDER) != 1:
        return (
            f"draft contains the {PLACEHOLDER} placeholder "
            f"{stripped.count(PLACEHOLDER)} times, expected exactly once"
        )

    if len(stripped) > budget:
        return f"draft is {len(stripped)} chars, over the {budget} limit"

    lowered = stripped.lower()
    for marker in _LINK_MARKERS:
        if marker in lowered:
            return f"draft contains a link-like token ({marker!r})"

    found_digit = _ANY_DIGIT.search(stripped)
    if found_digit is not None:
        return f"draft contains the digit {found_digit.group()!r}; the template must carry no numbers"

    return None


def _drafted_template(root_cause: str) -> DraftedTemplate:
    if root_cause in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[root_cause]

    base = TEMPLATES.get(root_cause, FALLBACK_TEMPLATE)

    if not settings.notification_llm_enabled:
        result = DraftedTemplate(
            template=base,
            source="template",
            reasoning="built-in template used verbatim -- LLM personalization disabled by config",
        )
        _TEMPLATE_CACHE[root_cause] = result
        return result

    # The rendered amount replaces the placeholder, so the length budget has
    # to allow for it -- checked against a generous rupee width rather than
    # any one transaction's amount, since this template is shared.
    budget = settings.notification_max_chars - len("₹00,00,000") + len(PLACEHOLDER)

    provider = llm.get_provider()
    user_content = (
        f"Template:\n{base}\n\n"
        f"Failure cause: {root_cause}.\n"
        f"Hard limit: {budget} characters, placeholder included."
    )

    try:
        candidate = provider.draft_text(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            max_tokens=300,
        )
    except Exception as exc:
        result = DraftedTemplate(
            template=base,
            source="template",
            reasoning=f"built-in template used verbatim -- LLM draft failed ({exc})",
        )
        _TEMPLATE_CACHE[root_cause] = result
        return result

    rejection = _rejection_reason(candidate, budget)
    if rejection is not None:
        result = DraftedTemplate(
            template=base,
            source="template",
            reasoning=f"built-in template used verbatim -- LLM draft rejected by content guard: {rejection}",
        )
    else:
        result = DraftedTemplate(
            template=candidate.strip(),
            source=f"llm:{provider.name}",
            reasoning=(
                "LLM-personalized template, accepted by the content guard (placeholder intact, "
                "no digits, no links, within length budget); amount substituted afterwards"
            ),
        )

    _TEMPLATE_CACHE[root_cause] = result
    return result


def draft(root_cause: str, amount_paise: int) -> Notification:
    drafted = _drafted_template(root_cause)
    return Notification(
        body=drafted.template.replace(PLACEHOLDER, format_inr(amount_paise)),
        source=drafted.source,
        reasoning=drafted.reasoning,
    )
