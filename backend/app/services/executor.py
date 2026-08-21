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
