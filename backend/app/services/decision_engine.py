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

# Visa/Mastercard decline taxonomy: only "soft" declines (temporary --
# issuer busy, insufficient funds right now) may ever be retried; "hard"
# declines (fraud, or a decline that should redirect rather than retry the
# same instrument) must not be. This is purely observational labeling of the
# behavior ROOT_CAUSE_ACTIONS already encodes -- card_declined's one action
# (suggest_alternate_method) redirects rather than retrying the same card,
# and possible_fraud gets zero actions -- so nothing here changes what the
# engine does, only makes the real-world rule it's already following
# explicit and citable. Nothing enforces these two dicts stay in sync (same
# unenforced relationship executor.SUCCESS_PROBABILITIES already has to
# ROOT_CAUSE_ACTIONS).
DECLINE_TYPE: dict[str, str] = {
    "insufficient_funds": "soft",
    "gateway_timeout": "soft",
    "auth_failure": "soft",
    "network_drop": "soft",
    "card_declined": "hard",
    "possible_fraud": "hard",
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

    if attempts_so_far >= settings.network_retry_ceiling:
        return Decision(
            action=None,
            escalate=True,
            reasoning=(
                f"attempts_so_far {attempts_so_far} >= network compliance ceiling "
                f"{settings.network_retry_ceiling} (Visa/Mastercard card-network "
                "reattempt-limit rule) -- no further automated retries permitted"
            ),
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
