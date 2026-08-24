from fastapi import APIRouter

from app.config import settings
from app.schemas import ConfigRulesOut
from app.services.decision_engine import DECLINE_TYPE, ROOT_CAUSE_ACTIONS

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/rules", response_model=ConfigRulesOut)
def get_rules():
    return ConfigRulesOut(
        root_cause_actions=ROOT_CAUSE_ACTIONS,
        decline_type=DECLINE_TYPE,
        confidence_threshold=settings.confidence_threshold,
        fraud_risk_score_threshold=settings.fraud_risk_score_threshold,
        network_retry_ceiling=settings.network_retry_ceiling,
        velocity_window_minutes=settings.velocity_window_minutes,
        velocity_threshold_count=settings.velocity_threshold_count,
        ip_velocity_threshold_count=settings.ip_velocity_threshold_count,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
        payday_lookahead_days=settings.payday_lookahead_days,
        webhook_ingestion_enabled=bool(settings.razorpay_webhook_secret),
        llm_provider=settings.llm_provider,
        classification_samples=settings.classification_samples,
        razorpay_execution_enabled=settings.razorpay_execution_enabled,
    )
