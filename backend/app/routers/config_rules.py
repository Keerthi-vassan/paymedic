from fastapi import APIRouter

from app.config import settings
from app.schemas import ConfigRulesOut
from app.services.decision_engine import ROOT_CAUSE_ACTIONS

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/rules", response_model=ConfigRulesOut)
def get_rules():
    return ConfigRulesOut(
        root_cause_actions=ROOT_CAUSE_ACTIONS,
        confidence_threshold=settings.confidence_threshold,
        fraud_risk_score_threshold=settings.fraud_risk_score_threshold,
        velocity_window_minutes=settings.velocity_window_minutes,
        velocity_threshold_count=settings.velocity_threshold_count,
        llm_provider=settings.llm_provider,
    )
