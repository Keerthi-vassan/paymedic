"""Generates a realistic, reproducible batch of simulated failed-payment events.

Root causes are weighted, ~17% of rows are deliberately ambiguous (masked
error_reason) so they miss every deterministic classifier rule and must be
routed to the LLM fallback, and one small cluster is constructed as a
card-testing / fraud pattern: each individual transaction in the cluster looks
like an ordinary gateway timeout (low risk_score, benign error_reason), so the
per-transaction classifier confidently mislabels it and the decision engine
issues a bounded retry. Only a later cross-transaction velocity check (the
safety monitor, built in a later phase) can catch the pattern -- that's the
deliberate "agent was wrong, caught itself" case.

Error fields mirror the shape of Razorpay's real Payment entity (error_code /
error_source / error_step / error_reason) rather than a single flat invented
code+description pair -- error_code is deliberately a coarse 3-value enum
(BAD_REQUEST_ERROR/GATEWAY_ERROR/SERVER_ERROR, matching Razorpay's real
taxonomy) too coarse on its own to drive 6-way root-cause classification, so
the classifier keys off the fine-grained error_reason instead (see
app/services/classifier.py). Amounts are stored as integers in paise (the
smallest currency subunit), matching Razorpay's real amount convention --
never as rupee floats.
"""

import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

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

# Mirrors Razorpay's real Payment entity error shape: a coarse `code`, the
# `source`/`step` of failure, and a fine-grained `reasons` pool (the actual
# `error_reason` enum Razorpay documents, e.g. "incorrect_otp").
ERROR_META = {
    "insufficient_funds": {
        "code": "BAD_REQUEST_ERROR",
        "source": "customer",
        "step": "payment_authorization",
        "reasons": ["insufficient_funds", "low_balance"],
    },
    "gateway_timeout": {
        "code": "GATEWAY_ERROR",
        "source": "gateway",
        "step": "payment_authorization",
        "reasons": ["gateway_timeout_error", "gateway_technical_error", "bank_technical_error"],
    },
    "auth_failure": {
        "code": "GATEWAY_ERROR",
        "source": "customer",
        "step": "payment_authentication",
        "reasons": ["incorrect_otp", "authentication_failed", "otp_timeout"],
    },
    "network_drop": {
        "code": "GATEWAY_ERROR",
        "source": "customer",
        "step": "payment_authorization",
        "reasons": ["connection_timeout", "customer_connection_break"],
    },
    "card_declined": {
        "code": "GATEWAY_ERROR",
        "source": "bank",
        "step": "payment_authorization",
        "reasons": ["issuer_declined", "do_not_honor", "card_declined"],
    },
    "possible_fraud": {
        "code": "GATEWAY_ERROR",
        "source": "bank",
        "step": "payment_authorization",
        # Deliberately the same pool as card_declined -- a fraud attempt looks
        # exactly like an ordinary decline at the error-field level, which is
        # the point (only risk_score/velocity gives it away).
        "reasons": ["issuer_declined", "do_not_honor", "card_declined"],
    },
}

# Only error_reason is masked for ambiguous rows -- error_code/source/step
# stay populated, since a real system still knows the coarse category even
# when the specific reason is unclear.
AMBIGUOUS_ERROR_REASONS = [None, "payment_failed", "processing_error"]

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
IP_CLUSTER_SIZE = 4

# Synthetic IPs are drawn from RFC 5737 documentation ranges only, so they
# never resemble real addresses.
IP_TEST_RANGES = [(192, 0, 2), (198, 51, 100), (203, 0, 113)]

# Fixed so the batch (including every failed_at timestamp) is byte-identical
# across runs for the same (count, seed) -- required for reproducible demo
# numbers in the README/pitch video.
DEFAULT_REFERENCE_TIME = datetime(2026, 8, 22, 12, 0, 0)


def _make_instrument_id(rng: random.Random, payment_method: str) -> str:
    if payment_method == "upi":
        return f"vpa_{uuid.UUID(int=rng.getrandbits(128)).hex[:12]}"
    return f"card_{uuid.UUID(int=rng.getrandbits(128)).hex[:12]}"


def _make_ip_address(rng: random.Random) -> str:
    a, b, c = rng.choice(IP_TEST_RANGES)
    return f"{a}.{b}.{c}.{rng.randint(1, 254)}"


def _base_row(rng: random.Random, faker: Faker, root_cause: str, failed_at: datetime) -> dict:
    payment_method = rng.choice(PAYMENT_METHODS)
    meta = ERROR_META[root_cause]
    error_reason = rng.choice(meta["reasons"])

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
        "amount": rng.randint(10_000, 5_000_000),  # paise: ₹100-₹50,000
        "currency": "INR",
        "payment_method": payment_method,
        "payment_instrument_id": _make_instrument_id(rng, payment_method),
        "issuer_bank": rng.choice(ISSUER_BANKS),
        "ip_address": _make_ip_address(rng),
        "error_code": meta["code"],
        "error_source": meta["source"],
        "error_step": meta["step"],
        "error_reason": error_reason,
        "failed_at": failed_at,
        "network_type": rng.choice(NETWORK_TYPES),
        "latency_ms": latency_ms,
        "risk_score": risk_score,
        "true_root_cause": root_cause,
        "status": "open",
        "final_action": None,
        "total_attempts": 0,
        "recovered_amount": 0,
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
    amounts = [100, 500, 2000, 5000][:FRAUD_CLUSTER_SIZE]  # paise: ₹1/₹5/₹20/₹50
    rows = []
    for i, amount in enumerate(amounts):
        failed_at = cluster_start + timedelta(minutes=i * rng.randint(2, 5))
        rows.append(
            {
                "transaction_id": f"txn_{uuid.UUID(int=rng.getrandbits(128)).hex[:16]}",
                "customer_id": f"cust_{uuid.UUID(int=rng.getrandbits(128)).hex[:10]}",
                "amount": amount,
                "currency": "INR",
                "payment_method": "card",
                "payment_instrument_id": instrument_id,
                "issuer_bank": rng.choice(ISSUER_BANKS),
                # Independently random per row (like customer_id) -- this
                # cluster's shared identifier is the instrument, not the IP;
                # sharing an IP too would accidentally also trip the
                # IP-velocity check below.
                "ip_address": _make_ip_address(rng),
                # Disguised as an ordinary gateway timeout at the error-field
                "error_code": "GATEWAY_ERROR",
                "error_source": "gateway",
                "error_step": "payment_authorization",
                "error_reason": rng.choice(["gateway_timeout_error", "gateway_technical_error"]),
                "failed_at": failed_at,
                "network_type": rng.choice(NETWORK_TYPES),
                "latency_ms": rng.randint(500, 2000),
                "risk_score": round(rng.uniform(0.3, 0.6), 2),
                "true_root_cause": "possible_fraud",
                "status": "open",
                "final_action": None,
                "total_attempts": 0,
                "recovered_amount": 0,
                "resolved_at": None,
            }
        )
    return rows


def _make_ip_velocity_cluster(rng: random.Random, now: datetime) -> list[dict]:
    """The inverse of the card-testing cluster: several DISTINCT instruments
    and DISTINCT customers, all sharing one IP address, minutes apart -- a
    distributed card-testing pattern (many different stolen cards tried from
    one source) rather than one card repeatedly. Each row individually looks
    like an ordinary decline; only the IP-based cross-transaction check
    catches the shared-source pattern.
    """
    shared_ip = _make_ip_address(rng)
    cluster_start = now - timedelta(days=rng.randint(1, 10), hours=rng.randint(0, 23))
    rows = []
    for i in range(IP_CLUSTER_SIZE):
        failed_at = cluster_start + timedelta(minutes=i * rng.randint(2, 5))
        payment_method = rng.choice(["card", "upi"])
        rows.append(
            {
                "transaction_id": f"txn_{uuid.UUID(int=rng.getrandbits(128)).hex[:16]}",
                "customer_id": f"cust_{uuid.UUID(int=rng.getrandbits(128)).hex[:10]}",
                "amount": rng.randint(10_000, 500_000),  # paise: ₹100-₹5,000
                "currency": "INR",
                "payment_method": payment_method,
                "payment_instrument_id": _make_instrument_id(rng, payment_method),
                "issuer_bank": rng.choice(ISSUER_BANKS),
                "ip_address": shared_ip,
                # Disguised as an ordinary card/gateway decline at the error-field level.
                "error_code": "GATEWAY_ERROR",
                "error_source": "bank",
                "error_step": "payment_authorization",
                "error_reason": rng.choice(["issuer_declined", "do_not_honor", "gateway_timeout_error"]),
                "failed_at": failed_at,
                "network_type": rng.choice(NETWORK_TYPES),
                "latency_ms": rng.randint(200, 1500),
                "risk_score": round(rng.uniform(0.3, 0.6), 2),
                "true_root_cause": "possible_fraud",
                "status": "open",
                "final_action": None,
                "total_attempts": 0,
                "recovered_amount": 0,
                "resolved_at": None,
            }
        )
    return rows


def _make_network_ceiling_demo_row(rng: random.Random, now: datetime) -> dict:
    """One transaction pre-seeded at the real Visa/Mastercard reattempt
    ceiling (settings.network_retry_ceiling), as if it had already
    accumulated that many attempts before this batch -- so the decision
    engine's network-compliance check has an actual on-screen moment in the
    demo instead of only being reachable in a unit test (every per-cause cap
    in ROOT_CAUSE_ACTIONS tops out at 3, well under the ceiling). An ordinary,
    undisguised soft-decline cause (unmasked error_reason, so it classifies
    deterministically) with fresh, unshared identifiers -- isolated from both
    fraud clusters.
    """
    root_cause = "gateway_timeout"
    meta = ERROR_META[root_cause]
    failed_at = now - timedelta(days=rng.randint(0, 14), hours=rng.randint(0, 23))
    payment_method = "card"
    return {
        "transaction_id": f"txn_{uuid.UUID(int=rng.getrandbits(128)).hex[:16]}",
        "customer_id": f"cust_{uuid.UUID(int=rng.getrandbits(128)).hex[:10]}",
        "amount": rng.randint(10_000, 5_000_000),
        "currency": "INR",
        "payment_method": payment_method,
        "payment_instrument_id": _make_instrument_id(rng, payment_method),
        "issuer_bank": rng.choice(ISSUER_BANKS),
        "ip_address": _make_ip_address(rng),
        "error_code": meta["code"],
        "error_source": meta["source"],
        "error_step": meta["step"],
        "error_reason": rng.choice(meta["reasons"]),
        "failed_at": failed_at,
        "network_type": rng.choice(NETWORK_TYPES),
        "latency_ms": rng.randint(500, 2000),
        "risk_score": round(rng.uniform(0.05, 0.5), 2),
        "true_root_cause": root_cause,
        "status": "open",
        "final_action": None,
        "total_attempts": settings.network_retry_ceiling,
        "recovered_amount": 0,
        "resolved_at": None,
    }


def generate_failed_payments(
    count: int = 100,
    seed: int = 42,
    reference_time: datetime | None = None,
) -> list[dict]:
    rng = random.Random(seed)
    faker = Faker()
    faker.seed_instance(seed)

    now = reference_time or DEFAULT_REFERENCE_TIME
    # Fixed order: all three special-row groups draw from the same rng
    # stream, so this order is now baked into seed=42 reproducibility.
    cluster_rows = _make_card_testing_cluster(rng, faker, now)
    ip_cluster_rows = _make_ip_velocity_cluster(rng, now)
    ceiling_row = _make_network_ceiling_demo_row(rng, now)
    special_rows = cluster_rows + ip_cluster_rows + [ceiling_row]

    remaining = max(count - len(special_rows), 0)
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
        row["error_reason"] = rng.choice(AMBIGUOUS_ERROR_REASONS)

    rows.extend(special_rows)
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
