"""
Recovery decision engine. Pure, rule-gated, and deliberately dumb: it takes
only structured fields (never raw LLM text) and never moves money itself. This
is the one place stopping rules are enforced -- fraud is never retried, and
attempts never exceed the per-cause cap -- so it's unit-tested directly.
"""

from dataclasses import dataclass

from app.config import settings

# (action sequence by attempt index, max attempts)
#
# insufficient_funds gets a notify-then-retry sequence rather than a single
# reminder: it is the largest failure bucket in the industry (~34% of failed
# recurring payments) and the most time-recoverable one, because nothing
# about the customer's intent failed -- their balance was short at that
# moment, and balances refill on salary credit. Notifying and then never
# re-attempting the charge leaves the single most recoverable category
# dependent entirely on the customer coming back by hand. The two retries
# are spaced by executor.RESOLUTION_DELAY_MINUTES and timed by
# retry_scheduler (which aligns them to a salary-credit window), landing the
# full sequence ~13 days out -- inside the industry 3-5 attempts / 10-14 day
# envelope, and far under the network compliance ceiling.
ROOT_CAUSE_ACTIONS: dict[str, list[str]] = {
    "insufficient_funds": ["send_reminder", "retry_with_backoff", "retry_with_backoff"],
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

# Which bounded actions re-attempt the charge against the same instrument, as
# opposed to redirecting the customer (suggest_alternate_method) or notifying
# them (send_reminder). Defined here, next to DECLINE_TYPE, because "a retry
# against a hard decline" is the exact combination the card networks fine
# merchants for -- metrics.py measures it as a genuine false action, and
# retry_scheduler.py uses it to decide what payday alignment applies to.
RETRY_ACTIONS: frozenset[str] = frozenset({"retry_immediate", "retry_with_backoff"})


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
