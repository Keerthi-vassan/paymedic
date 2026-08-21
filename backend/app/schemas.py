from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FailedPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    customer_id: str
    amount: float
    currency: str
    payment_method: str
    payment_instrument_id: str
    issuer_bank: str
    error_code: str | None
    error_description: str
    failed_at: datetime
    network_type: str
    latency_ms: int
    risk_score: float
    true_root_cause: str
    status: str
    final_action: str | None
    total_attempts: int
    recovered_amount: float
    resolved_at: datetime | None


class GenerateBatchResponse(BaseModel):
    count: int
    seed: int


class PaymentsListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[FailedPaymentOut]
