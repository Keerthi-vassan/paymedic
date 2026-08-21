from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import MetricsSummaryOut, RootCauseBreakdownRowOut, TimelinePointOut
from app.services import metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary", response_model=MetricsSummaryOut)
def summary(db: Session = Depends(get_db)):
    return metrics.compute_summary(db)


@router.get("/root-cause-breakdown", response_model=list[RootCauseBreakdownRowOut])
def root_cause_breakdown(db: Session = Depends(get_db)):
    return metrics.compute_root_cause_breakdown(db)


@router.get("/timeline", response_model=list[TimelinePointOut])
def timeline(db: Session = Depends(get_db)):
    return metrics.compute_timeline(db)
