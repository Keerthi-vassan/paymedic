"""Shared contract every LLM provider adapter implements. The classifier only
ever sees this interface -- it never decides or executes a recovery action,
it only emits a (root_cause, confidence, reasoning) label that the rule-gated
decision engine then acts on independently.
"""

import json
from dataclasses import dataclass
from typing import Protocol

from app.models import FailedPayment

ROOT_CAUSES = [
    "insufficient_funds",
    "gateway_timeout",
    "auth_failure",
    "network_drop",
    "card_declined",
    "possible_fraud",
]

SYSTEM_PROMPT = (
    "You are a root-cause classification component inside a bounded payment-recovery "
    "system. You classify why a payment failed. You do NOT decide or execute any "
    "recovery action -- a separate rule-based engine does that using only your label. "
    "Choose exactly one of: insufficient_funds, gateway_timeout, auth_failure, "
    "network_drop, card_declined, possible_fraud. If evidence is mixed, pick the "
    "closest category and express uncertainty via confidence -- never invent a new "
    "category."
)

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string", "enum": ROOT_CAUSES},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string", "maxLength": 240},
    },
    "required": ["root_cause", "confidence", "reasoning"],
    "additionalProperties": False,
}


def build_user_content(payment: FailedPayment) -> str:
    return json.dumps(
        {
            "error_code": payment.error_code,
            "error_source": payment.error_source,
            "error_step": payment.error_step,
            "error_reason": payment.error_reason,
            "payment_method": payment.payment_method,
            "amount": payment.amount,
            "attempt_number": payment.total_attempts + 1,
            "latency_ms": payment.latency_ms,
            "risk_score": payment.risk_score,
        }
    )


@dataclass
class LLMClassification:
    root_cause: str
    confidence: float
    reasoning: str


def validate_classification(raw: dict) -> LLMClassification:
    """Defense in depth: a malformed/hallucinated response must never reach the
    decision engine as if it were a valid label. Falls back to 'ambiguous' with
    zero confidence, which the decision engine's confidence threshold turns
    into a safe escalation rather than a silent wrong action.
    """
    root_cause = raw.get("root_cause")
    if root_cause not in ROOT_CAUSES:
        return LLMClassification(
            root_cause="ambiguous",
            confidence=0.0,
            reasoning=f"LLM returned an unrecognized root_cause '{root_cause}' -- treating as ambiguous",
        )

    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence"))))
    except (TypeError, ValueError):
        confidence = 0.0

    reasoning = str(raw.get("reasoning", ""))[:240]
    return LLMClassification(root_cause=root_cause, confidence=confidence, reasoning=reasoning)


class LLMProvider(Protocol):
    name: str

    def classify_ambiguous(self, payment: FailedPayment) -> LLMClassification: ...
