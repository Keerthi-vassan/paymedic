from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FailedPayment(Base):
    __tablename__ = "failed_payments"

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String, default="INR")
    payment_method: Mapped[str] = mapped_column(String)
    payment_instrument_id: Mapped[str] = mapped_column(String)
    issuer_bank: Mapped[str] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_description: Mapped[str] = mapped_column(String)
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
    recovered_amount: Mapped[float] = mapped_column(Float, default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
