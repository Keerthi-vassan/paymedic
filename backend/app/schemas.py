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
    blocked: int
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


class MetricsSummaryOut(BaseModel):
    total_transactions: int
    total_at_risk_amount: float
    total_recovered_amount: float
    recovery_rate: float
    escalation_rate: float
    blocked_rate: float
    false_action_rate: float
    fraud_block_rate: float
    avg_time_to_recovery_minutes: float | None
    median_time_to_recovery_minutes: float | None


class RootCauseBreakdownRowOut(BaseModel):
    root_cause: str
    total: int
    recovered: int
    escalated: int
    blocked: int
    open: int
    recovery_rate: float


class TimelinePointOut(BaseModel):
    resolved_at: str
    cumulative_recovered_amount: float


class ConfigRulesOut(BaseModel):
    root_cause_actions: dict[str, list[str]]
    confidence_threshold: float
    fraud_risk_score_threshold: float
    velocity_window_minutes: int
    velocity_threshold_count: int
    llm_provider: str
