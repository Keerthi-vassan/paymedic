from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FailedPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    customer_id: str
    amount: int  # paise
    currency: str
    payment_method: str
    payment_instrument_id: str
    issuer_bank: str
    ip_address: str
    error_code: str
    error_source: str
    error_step: str
    error_reason: str | None
    failed_at: datetime
    network_type: str
    latency_ms: int
    risk_score: float
    true_root_cause: str
    ingest_source: str
    status: str
    final_action: str | None
    total_attempts: int
    recovered_amount: int  # paise
    resolved_at: datetime | None
    is_real: bool
    real_execution_verified: bool
    gateway_order_id: str | None
    gateway_payment_id: str | None


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
    total_recovered_amount: int  # paise


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
    scheduled_at: datetime | None
    created_at: datetime
    execution_source: str | None
    gateway_order_id: str | None
    gateway_payment_id: str | None
    gateway_status: str | None
    notification_body: str | None


class AuditListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditLogOut]


class MetricsSummaryOut(BaseModel):
    total_transactions: int
    total_at_risk_amount: int  # paise
    total_recovered_amount: int  # paise
    recovery_rate: float
    escalation_rate: float
    blocked_rate: float
    false_action_rate: float
    false_action_count: int
    safety_override_rate: float
    fraud_block_rate: float
    avg_time_to_recovery_minutes: float | None
    median_time_to_recovery_minutes: float | None
    real_candidate_count: int
    real_execution_verified_count: int


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
    cumulative_recovered_amount: int  # paise


class ClassifierPathRowOut(BaseModel):
    path: str
    total: int
    correct: int
    accuracy: float


class ConfusionRowOut(BaseModel):
    true_root_cause: str
    total: int
    predicted: dict[str, int]


class CalibrationBucketOut(BaseModel):
    label: str
    lower: float
    upper: float
    total: int
    correct: int
    accuracy: float
    mean_confidence: float


class ClassifierMetricsOut(BaseModel):
    total_classified: int
    graded: int
    ungraded: int
    overall_accuracy: float
    paths: list[ClassifierPathRowOut]
    confusion: list[ConfusionRowOut]
    calibration: list[CalibrationBucketOut]
    confidence_threshold: float
    above_threshold_total: int
    above_threshold_accuracy: float
    below_threshold_total: int
    below_threshold_accuracy: float


class ConfigRulesOut(BaseModel):
    root_cause_actions: dict[str, list[str]]
    decline_type: dict[str, str]
    confidence_threshold: float
    fraud_risk_score_threshold: float
    network_retry_ceiling: int
    velocity_window_minutes: int
    velocity_threshold_count: int
    ip_velocity_threshold_count: int
    quiet_hours_start: int
    quiet_hours_end: int
    payday_lookahead_days: int
    llm_provider: str
    classification_samples: int
    webhook_ingestion_enabled: bool
    razorpay_execution_enabled: bool
