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
        llm_provider=settings.llm_provider,
        razorpay_execution_enabled=settings.razorpay_execution_enabled,
    )
