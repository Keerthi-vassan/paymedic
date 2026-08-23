"""Simulates action outcomes, since there's no real payment gateway. Success
probabilities are documented assumptions (illustrative, not measured), not
unexplained randomness: transient failures (timeouts, dropped connections)
recover better on retry than issuer-declines or balance shortfalls do, and
recovery odds diminish with each further attempt.

Outcomes are deterministic per (transaction_id, attempt_number) -- derived from
a hash rather than a shared RNG stream -- so re-running the pipeline for the
same transaction always reproduces the same result regardless of batch order
or which other transactions were processed alongside it.
"""

import hashlib

SUCCESS_PROBABILITIES: dict[str, list[float]] = {
    "insufficient_funds": [0.30],
    "gateway_timeout": [0.65, 0.40, 0.20],
    "auth_failure": [0.55, 0.35],
    "network_drop": [0.70, 0.45, 0.25],
    "card_declined": [0.50],
    "possible_fraud": [],
}

# How long each action takes to resolve, in simulated minutes, keyed by
# (action, global attempt_number). Grounded in the industry pattern of 3-5
# retry attempts spread over 10-14 days rather than resolved back-to-back:
# retry_immediate stays near-instant (a genuine same-session gateway retry);
# retry_with_backoff escalates by attempt number (2 / 5 / 7 days out), so a
# full gateway_timeout/network_drop sequence (immediate, backoff, backoff)
# lands ~12 days out by its final attempt, inside the 10-14 day envelope, and
# a shorter auth_failure sequence (backoff, backoff, cap 2) lands ~7 days
# out; suggest_alternate_method is an in-session customer decision; and
# send_reminder is dunning-style (days, not hours -- insufficient-funds
# recovery genuinely benefits from waiting for a payday/top-up, which is also
# why SUCCESS_PROBABILITIES["insufficient_funds"] is a low single-shot
# number). Deterministic by design, like SUCCESS_PROBABILITIES -- a
# documented assumption, not jittered/randomized.
RESOLUTION_DELAY_MINUTES: dict[tuple[str, int], float] = {
    ("retry_immediate", 1): 5,
    ("retry_immediate", 2): 5,
    ("retry_immediate", 3): 5,
    ("retry_with_backoff", 1): 2 * 24 * 60,
    ("retry_with_backoff", 2): 5 * 24 * 60,
    ("retry_with_backoff", 3): 7 * 24 * 60,
    ("suggest_alternate_method", 1): 30,
    ("send_reminder", 1): 3 * 24 * 60,
}


def resolution_delay_minutes(action: str, attempt_number: int) -> float:
    return RESOLUTION_DELAY_MINUTES.get((action, attempt_number), 0)


def _deterministic_unit_interval(transaction_id: str, attempt_number: int) -> float:
    digest = hashlib.sha256(f"{transaction_id}:{attempt_number}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def execute(transaction_id: str, root_cause: str, attempt_number: int) -> str:
    """attempt_number is 1-indexed. Returns 'success' or 'fail'."""
    probabilities = SUCCESS_PROBABILITIES.get(root_cause, [])
    if attempt_number < 1 or attempt_number > len(probabilities):
        return "fail"

    success_probability = probabilities[attempt_number - 1]
    roll = _deterministic_unit_interval(transaction_id, attempt_number)
    return "success" if roll < success_probability else "fail"
