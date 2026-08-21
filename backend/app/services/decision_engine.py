"""
Recovery decision engine. Pure, rule-gated, and deliberately dumb: it takes
only structured fields (never raw LLM text) and never moves money itself. This
is the one place stopping rules are enforced -- fraud is never retried, and
attempts never exceed the per-cause cap -- so it's unit-tested directly.
"""

from dataclasses import dataclass

from app.config import settings

# (action sequence by attempt index, max attempts)
ROOT_CAUSE_ACTIONS: dict[str, list[str]] = {
    "insufficient_funds": ["send_reminder"],
    "gateway_timeout": ["retry_immediate", "retry_with_backoff", "retry_with_backoff"],
    "auth_failure": ["retry_with_backoff", "retry_with_backoff"],
    "network_drop": ["retry_immediate", "retry_with_backoff", "retry_with_backoff"],
    "card_declined": ["suggest_alternate_method"],
    "possible_fraud": [],
}


@dataclass
class Decision:
    action: str  # None when escalate is True
    escalate: bool
    reasoning: str


def decide(root_cause: str, confidence: float, risk_score: float, attempts_so_far: int) -> Decision:
    if risk_score >= settings.fraud_risk_score_threshold:
        return Decision(
            action=None,
            escalate=True,
            reasoning=(
                f"risk_score {risk_score:.2f} >= fraud threshold "
                f"{settings.fraud_risk_score_threshold:.2f} -- no automated action per policy"
            ),
        )

    if root_cause == "possible_fraud":
        return Decision(
            action=None,
            escalate=True,
            reasoning="fraud flag -- no automated action per policy",
        )

    if confidence < settings.confidence_threshold:
        return Decision(
            action=None,
            escalate=True,
            reasoning=(
                f"classifier confidence {confidence:.2f} below threshold "
                f"{settings.confidence_threshold:.2f} -- human review required"
            ),
        )

    action_sequence = ROOT_CAUSE_ACTIONS.get(root_cause, [])
    max_attempts = len(action_sequence)

    if attempts_so_far >= max_attempts:
        return Decision(
            action=None,
            escalate=True,
            reasoning=f"retry cap reached ({attempts_so_far}/{max_attempts} attempts for {root_cause})",
        )

    action = action_sequence[attempts_so_far]
    return Decision(
        action=action,
        escalate=False,
        reasoning=f"attempt {attempts_so_far + 1}/{max_attempts} for {root_cause}: {action}",
    )
