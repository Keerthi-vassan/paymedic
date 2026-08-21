"""Root-cause classification: deterministic rules first, LLM fallback for the
rest. Fraud is always decided by the risk_score rule below -- it is never
delegated to the LLM, since it's the one safety-critical branch. The LLM
provider is swappable (see app/services/llm/) and, like the rules, only ever
emits a label -- it never decides or executes a recovery action itself.
"""

from dataclasses import dataclass

from app.config import settings
from app.models import FailedPayment
from app.services import llm

ERROR_CODE_TO_ROOT_CAUSE = {
    "INSUFFICIENT_FUNDS": "insufficient_funds",
    "INSUFFICIENT_BALANCE": "insufficient_funds",
    "GATEWAY_TIMEOUT": "gateway_timeout",
    "GATEWAY_ERROR": "gateway_timeout",
    "BANK_DOWN": "gateway_timeout",
    "AUTHENTICATION_ERROR": "auth_failure",
    "OTP_MISMATCH": "auth_failure",
    "INVALID_OTP": "auth_failure",
    "NETWORK_ERROR": "network_drop",
    "CONNECTION_RESET": "network_drop",
    "CARD_DECLINED": "card_declined",
    "ISSUER_DECLINED": "card_declined",
    "DO_NOT_HONOR": "card_declined",
}

AMBIGUOUS_ROOT_CAUSE = "ambiguous"


@dataclass
class ClassificationResult:
    root_cause: str
    confidence: float
    reasoning: str
    source: str  # rule_engine | llm:<provider> | llm:<provider>:error


def classify(payment: FailedPayment) -> ClassificationResult:
    if payment.risk_score >= settings.fraud_risk_score_threshold:
        return ClassificationResult(
            root_cause="possible_fraud",
            confidence=1.0,
            reasoning=(
                f"risk_score {payment.risk_score:.2f} >= fraud threshold "
                f"{settings.fraud_risk_score_threshold:.2f} -- rule-based fraud flag"
            ),
            source="rule_engine",
        )

    if payment.error_code in ERROR_CODE_TO_ROOT_CAUSE:
        root_cause = ERROR_CODE_TO_ROOT_CAUSE[payment.error_code]
        return ClassificationResult(
            root_cause=root_cause,
            confidence=0.95,
            reasoning=f"error_code '{payment.error_code}' maps deterministically to {root_cause}",
            source="rule_engine",
        )

    # No deterministic rule matched -- ask the LLM. A failed/unreachable call
    # falls back to the same safe "ambiguous, zero confidence" shape a
    # malformed response would, so the decision engine escalates for human
    # review rather than silently skipping or misclassifying the transaction.
    provider = llm.get_provider()
    try:
        result = provider.classify_ambiguous(payment)
        return ClassificationResult(
            root_cause=result.root_cause,
            confidence=result.confidence,
            reasoning=result.reasoning,
            source=f"llm:{provider.name}",
        )
    except Exception as exc:
        return ClassificationResult(
            root_cause=AMBIGUOUS_ROOT_CAUSE,
            confidence=0.0,
            reasoning=f"LLM call failed ({exc}) -- escalating for human review",
            source=f"llm:{provider.name}:error",
        )
