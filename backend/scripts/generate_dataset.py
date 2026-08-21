"""Generates a realistic, reproducible batch of simulated failed-payment events.

Root causes are weighted, ~17% of rows are deliberately ambiguous (masked error
codes/generic descriptions) so they miss every deterministic classifier rule and
must be routed to the LLM fallback, and one small cluster is constructed as a
card-testing / fraud pattern: each individual transaction in the cluster looks
like an ordinary gateway timeout (low risk_score, benign error_code), so the
per-transaction classifier confidently mislabels it and the decision engine
issues a bounded retry. Only a later cross-transaction velocity check (the
safety monitor, built in a later phase) can catch the pattern -- that's the
deliberate "agent was wrong, caught itself" case.
"""

import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT_CAUSES = [
    "insufficient_funds",
    "gateway_timeout",
    "auth_failure",
    "network_drop",
    "card_declined",
    "possible_fraud",
]

ROOT_CAUSE_WEIGHTS = {
    "insufficient_funds": 25,
    "gateway_timeout": 20,
    "auth_failure": 15,
    "network_drop": 15,
    "card_declined": 20,
    "possible_fraud": 5,
}

ERROR_CODES = {
    "insufficient_funds": ["INSUFFICIENT_FUNDS", "INSUFFICIENT_BALANCE"],
    "gateway_timeout": ["GATEWAY_TIMEOUT", "GATEWAY_ERROR", "BANK_DOWN"],
    "auth_failure": ["AUTHENTICATION_ERROR", "OTP_MISMATCH", "INVALID_OTP"],
    "network_drop": ["NETWORK_ERROR", "CONNECTION_RESET"],
    "card_declined": ["CARD_DECLINED", "ISSUER_DECLINED", "DO_NOT_HONOR"],
    "possible_fraud": ["CARD_DECLINED", "DO_NOT_HONOR"],
}

ERROR_DESCRIPTIONS = {
    "insufficient_funds": [
        "Insufficient balance in account",
        "Available balance is less than the transaction amount",
    ],
    "gateway_timeout": [
        "Gateway did not respond in time",
        "Bank server timeout during authorization",
    ],
    "auth_failure": [
        "OTP verification failed",
        "Authentication declined by issuer",
    ],
    "network_drop": [
        "Connection lost during transaction",
        "Network error - request incomplete",
    ],
    "card_declined": [
        "Card declined by issuer",
        "Transaction not honored by issuing bank",
    ],
    "possible_fraud": [
        "Card declined by issuer",
        "Transaction not honored by issuing bank",
    ],
}

AMBIGUOUS_ERROR_CODES = [None, "UNKNOWN_ERROR", "PROCESSING_ERROR"]
AMBIGUOUS_DESCRIPTIONS = [
    "Payment could not be completed",
    "Something went wrong. Please try again.",
    "Transaction failed",
]

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]
ISSUER_BANKS = [
    "HDFC Bank",
    "ICICI Bank",
    "State Bank of India",
    "Axis Bank",
    "Kotak Mahindra Bank",
    "Yes Bank",
    "IDFC First Bank",
    "Punjab National Bank",
]
NETWORK_TYPES = ["wifi", "4g", "3g", "ethernet"]

AMBIGUOUS_RATE = 0.17
FRAUD_CLUSTER_SIZE = 4

# Fixed so the batch (including every failed_at timestamp) is byte-identical
# across runs for the same (count, seed) -- required for reproducible demo
# numbers in the README/pitch video.
DEFAULT_REFERENCE_TIME = datetime(2026, 8, 22, 12, 0, 0)


def _make_instrument_id(rng: random.Random, payment_method: str) -> str:
    if payment_method == "upi":
        return f"vpa_{uuid.UUID(int=rng.getrandbits(128)).hex[:12]}"
    return f"card_{uuid.UUID(int=rng.getrandbits(128)).hex[:12]}"


def _base_row(rng: random.Random, faker: Faker, root_cause: str, failed_at: datetime) -> dict:
    payment_method = rng.choice(PAYMENT_METHODS)
    error_code = rng.choice(ERROR_CODES[root_cause])
    error_description = rng.choice(ERROR_DESCRIPTIONS[root_cause])

    if root_cause == "network_drop":
        latency_ms = rng.randint(800, 3000)
    elif root_cause == "gateway_timeout":
        latency_ms = rng.randint(500, 2000)
    else:
        latency_ms = rng.randint(50, 400)

    if root_cause == "possible_fraud":
        risk_score = round(rng.uniform(0.85, 0.99), 2)
    else:
        risk_score = round(rng.uniform(0.05, 0.5), 2)

    return {
        "transaction_id": f"txn_{uuid.UUID(int=rng.getrandbits(128)).hex[:16]}",
        "customer_id": f"cust_{uuid.UUID(int=rng.getrandbits(128)).hex[:10]}",
        "amount": round(rng.uniform(100, 50000), 2),
        "currency": "INR",
        "payment_method": payment_method,
        "payment_instrument_id": _make_instrument_id(rng, payment_method),
        "issuer_bank": rng.choice(ISSUER_BANKS),
        "error_code": error_code,
        "error_description": error_description,
        "failed_at": failed_at,
        "network_type": rng.choice(NETWORK_TYPES),
        "latency_ms": latency_ms,
        "risk_score": risk_score,
        "true_root_cause": root_cause,
        "status": "open",
        "final_action": None,
        "total_attempts": 0,
        "recovered_amount": 0.0,
        "resolved_at": None,
    }


def _make_card_testing_cluster(rng: random.Random, faker: Faker, now: datetime) -> list[dict]:
    """A handful of transactions on one instrument, small increasing amounts,
    minutes apart -- a card-testing pattern. Each row individually looks like an
    ordinary gateway timeout with a low risk_score, so the per-transaction
    classifier and fraud rule both miss it; only a cross-transaction check can
    catch the pattern.
    """
    instrument_id = _make_instrument_id(rng, "card")
    cluster_start = now - timedelta(days=rng.randint(1, 10), hours=rng.randint(0, 23))
    amounts = [1, 5, 20, 50][:FRAUD_CLUSTER_SIZE]
    rows = []
    for i, amount in enumerate(amounts):
        failed_at = cluster_start + timedelta(minutes=i * rng.randint(2, 5))
        rows.append(
            {
                "transaction_id": f"txn_{uuid.UUID(int=rng.getrandbits(128)).hex[:16]}",
                "customer_id": f"cust_{uuid.UUID(int=rng.getrandbits(128)).hex[:10]}",
                "amount": float(amount),
                "currency": "INR",
                "payment_method": "card",
                "payment_instrument_id": instrument_id,
                "issuer_bank": rng.choice(ISSUER_BANKS),
                "error_code": "GATEWAY_TIMEOUT",
                "error_description": "Gateway did not respond in time",
                "failed_at": failed_at,
                "network_type": rng.choice(NETWORK_TYPES),
                "latency_ms": rng.randint(500, 2000),
                "risk_score": round(rng.uniform(0.3, 0.6), 2),
                "true_root_cause": "possible_fraud",
                "status": "open",
                "final_action": None,
                "total_attempts": 0,
                "recovered_amount": 0.0,
                "resolved_at": None,
            }
        )
    return rows


def generate_failed_payments(
    count: int = 100,
    seed: int = 42,
    reference_time: datetime | None = None,
) -> list[dict]:
    rng = random.Random(seed)
    faker = Faker()
    faker.seed_instance(seed)

    now = reference_time or DEFAULT_REFERENCE_TIME
    cluster_rows = _make_card_testing_cluster(rng, faker, now)

    remaining = max(count - len(cluster_rows), 0)
    categories = list(ROOT_CAUSE_WEIGHTS.keys())
    weights = list(ROOT_CAUSE_WEIGHTS.values())
    chosen_causes = rng.choices(categories, weights=weights, k=remaining)

    rows = []
    for root_cause in chosen_causes:
        failed_at = now - timedelta(
            days=rng.randint(0, 14),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        rows.append(_base_row(rng, faker, root_cause, failed_at))

    ambiguous_count = round(len(rows) * AMBIGUOUS_RATE)
    for row in rng.sample(rows, k=min(ambiguous_count, len(rows))):
        row["error_code"] = rng.choice(AMBIGUOUS_ERROR_CODES)
        row["error_description"] = rng.choice(AMBIGUOUS_DESCRIPTIONS)

    rows.extend(cluster_rows)
    rng.shuffle(rows)
    return rows


def main():
    from app.db import Base, SessionLocal, engine
    from app.models import FailedPayment

    Base.metadata.create_all(bind=engine)

    rows = generate_failed_payments()
    db = SessionLocal()
    try:
        db.query(FailedPayment).delete()
        db.bulk_insert_mappings(FailedPayment, rows)
        db.commit()
    finally:
        db.close()

    print(f"Generated {len(rows)} simulated failed payments.")


if __name__ == "__main__":
    main()
