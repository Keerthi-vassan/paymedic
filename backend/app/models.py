from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FailedPayment(Base):
    __tablename__ = "failed_payments"

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String)
    # Integer, in paise (smallest currency subunit) -- matches Razorpay's real
    # amount convention. Never a rupee float.
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String, default="INR")
    payment_method: Mapped[str] = mapped_column(String)
    payment_instrument_id: Mapped[str] = mapped_column(String)
    issuer_bank: Mapped[str] = mapped_column(String)
    # Cross-transaction fraud signal alongside payment_instrument_id: the
    # safety monitor also groups by this to catch many distinct instruments
    # sharing one IP (a distributed card-testing pattern the instrument-based
    # check alone can't see). Synthetic values only -- RFC 5737 TEST-NET
    # ranges, never real-looking IPs.
    ip_address: Mapped[str] = mapped_column(String)

    # Mirrors Razorpay's real Payment entity error shape: error_code is a
    # coarse enum (BAD_REQUEST_ERROR/GATEWAY_ERROR/SERVER_ERROR), error_source/
    # error_step describe where/when it failed, and error_reason is the
    # fine-grained value the classifier's deterministic rules key off (see
    # app/services/classifier.py) -- and the field masked for ambiguous rows.
    error_code: Mapped[str] = mapped_column(String)
    error_source: Mapped[str] = mapped_column(String)
    error_step: Mapped[str] = mapped_column(String)
    error_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    failed_at: Mapped[datetime] = mapped_column(DateTime)
    network_type: Mapped[str] = mapped_column(String)
    latency_ms: Mapped[int] = mapped_column(Integer)
    risk_score: Mapped[float] = mapped_column(Float)

    # Hidden ground truth used only for offline evaluation of the classifier,
    # never read by the classifier/decision engine/executor themselves.
    true_root_cause: Mapped[str] = mapped_column(String)

    status: Mapped[str] = mapped_column(String, default="open")
    final_action: Mapped[str | None] = mapped_column(String, nullable=True)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    recovered_amount: Mapped[int] = mapped_column(Integer, default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Marks this row as one of the small, fixed-count subset (see
    # RAZORPAY_REAL_TXN_COUNT) whose first action is attempted against a real
    # Razorpay test-mode order instead of the simulated hash-roll. Set only at
    # generation time, invisible to decision_engine/safety_monitor.
    is_real: Mapped[bool] = mapped_column(Boolean, default=False)
    # True only once a real gateway response was actually obtained for this
    # transaction -- a real candidate whose execution attempt fell back to
    # simulated stays is_real=True, real_execution_verified=False, and must
    # read as simulated everywhere in the UI.
    real_execution_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    gateway_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("failed_payments.transaction_id"))

    # classification | decision | action_execution | safety_override
    event_type: Mapped[str] = mapped_column(String)
    # rule_engine | llm | decision_engine | executor | safety_monitor
    source: Mapped[str] = mapped_column(String)

    root_cause: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String, nullable=True)
    reasoning: Mapped[str] = mapped_column(String)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)  # success | fail | pending | blocked
    attempt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When this attempt is projected to actually occur in a real system, per
    # realistic dunning/backoff spacing (see executor.resolution_delay_minutes)
    # -- None whenever the decision escalates, since there's no action to
    # schedule. Set once at "decision" time and never retroactively updated,
    # so it stays an honest historical snapshot even if a later
    # safety_override supersedes the transaction.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Populated only on action_execution events: which path actually produced
    # this outcome ("simulated" | "real_razorpay") and, when real, the raw
    # gateway references/status -- lets the audit trail and dashboard tell a
    # real Razorpay-verified outcome apart from the simulated majority instead
    # of blending them invisibly.
    execution_source: Mapped[str | None] = mapped_column(String, nullable=True)
    gateway_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    gateway_status: Mapped[str | None] = mapped_column(String, nullable=True)
