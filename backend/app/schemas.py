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


class PipelineRunRequest(BaseModel):
    transaction_ids: list[str] | None = None


class PipelineRunResponse(BaseModel):
    processed: int
    recovered: int
    escalated: int
    total_recovered_amount: float


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: str
    event_type: str
    source: str
    root_cause: str | None
    confidence: float | None
    action_taken: str | None
    reasoning: str
    outcome: str | None
    attempt_number: int | None
    created_at: datetime


class AuditListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditLogOut]
