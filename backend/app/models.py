from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
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
