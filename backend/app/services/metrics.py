"""Aggregate metrics computed directly from the batch -- every number here is
derived from the same FailedPayment/AuditLog rows the pipeline itself wrote,
not a separately tracked or asserted figure.
"""

from dataclasses import dataclass
from statistics import mean, median

from sqlalchemy.orm import Session

from app.models import FailedPayment


@dataclass
class MetricsSummary:
    total_transactions: int
    total_at_risk_amount: int  # paise
    total_recovered_amount: int  # paise
    recovery_rate: float
    escalation_rate: float
    blocked_rate: float
    false_action_rate: float
    fraud_block_rate: float
    avg_time_to_recovery_minutes: float | None
    median_time_to_recovery_minutes: float | None


@dataclass
class RootCauseBreakdownRow:
    root_cause: str
    total: int
    recovered: int
    escalated: int
    blocked: int
    open: int
    recovery_rate: float


@dataclass
class TimelinePoint:
    resolved_at: str
    cumulative_recovered_amount: int  # paise


def _pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def compute_summary(db: Session) -> MetricsSummary:
    payments = db.query(FailedPayment).all()
    total = len(payments)

    recovered = [p for p in payments if p.status == "recovered"]
    escalated = [p for p in payments if p.status == "escalated"]
    blocked = [p for p in payments if p.status == "blocked"]
    actioned = [p for p in payments if p.total_attempts > 0]
    fraud_cases = [p for p in payments if p.true_root_cause == "possible_fraud"]
    fraud_blocked = [p for p in fraud_cases if p.status in ("escalated", "blocked")]

    recovery_times_minutes = [
        (p.resolved_at - p.failed_at).total_seconds() / 60
        for p in recovered
        if p.resolved_at is not None
    ]

    return MetricsSummary(
        total_transactions=total,
        total_at_risk_amount=sum(p.amount for p in payments),
        total_recovered_amount=sum(p.recovered_amount for p in recovered),
        recovery_rate=_pct(len(recovered), total),
        escalation_rate=_pct(len(escalated), total),
        blocked_rate=_pct(len(blocked), total),
        false_action_rate=_pct(len(blocked), len(actioned)),
        fraud_block_rate=_pct(len(fraud_blocked), len(fraud_cases)),
        avg_time_to_recovery_minutes=(
            round(mean(recovery_times_minutes), 2) if recovery_times_minutes else None
        ),
        median_time_to_recovery_minutes=(
            round(median(recovery_times_minutes), 2) if recovery_times_minutes else None
        ),
    )


def compute_root_cause_breakdown(db: Session) -> list[RootCauseBreakdownRow]:
    payments = db.query(FailedPayment).all()
    root_causes = sorted({p.true_root_cause for p in payments})

    rows = []
    for root_cause in root_causes:
        group = [p for p in payments if p.true_root_cause == root_cause]
        recovered = sum(1 for p in group if p.status == "recovered")
        rows.append(
            RootCauseBreakdownRow(
                root_cause=root_cause,
                total=len(group),
                recovered=recovered,
                escalated=sum(1 for p in group if p.status == "escalated"),
                blocked=sum(1 for p in group if p.status == "blocked"),
                open=sum(1 for p in group if p.status == "open"),
                recovery_rate=_pct(recovered, len(group)),
            )
        )
    return rows


def compute_timeline(db: Session) -> list[TimelinePoint]:
    recovered = (
        db.query(FailedPayment)
        .filter(FailedPayment.status == "recovered", FailedPayment.resolved_at.isnot(None))
        .order_by(FailedPayment.resolved_at.asc())
        .all()
    )

    points = []
    running_total = 0
    for p in recovered:
        running_total += p.recovered_amount
        points.append(
            TimelinePoint(
                resolved_at=p.resolved_at.isoformat(),
                cumulative_recovered_amount=running_total,
            )
        )
    return points
