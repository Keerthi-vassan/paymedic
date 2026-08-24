"""Aggregate metrics computed directly from the batch -- every number here is
derived from the same FailedPayment/AuditLog rows the pipeline itself wrote,
not a separately tracked or asserted figure.
"""

from dataclasses import dataclass, field
from statistics import mean, median

from sqlalchemy.orm import Session

from app.config import settings
from app.models import UNKNOWN_ROOT_CAUSE, AuditLog, FailedPayment
from app.services.decision_engine import DECLINE_TYPE, RETRY_ACTIONS
from app.services.llm.base import ROOT_CAUSES


@dataclass
class MetricsSummary:
    total_transactions: int
    total_at_risk_amount: int  # paise
    total_recovered_amount: int  # paise
    recovery_rate: float
    escalation_rate: float
    blocked_rate: float
    # Actions the system took that ground truth says it should not have --
    # a retry against a true fraud case, or a retry against a true hard
    # decline. See _false_actions for why this is not the same thing as
    # safety_override_rate.
    false_action_rate: float
    false_action_count: int
    # How much of what the system actioned its own safety monitor later
    # retracted. Previously (mis)named false_action_rate; it measures the
    # monitor's catch volume, not the system's error rate.
    safety_override_rate: float
    fraud_block_rate: float
    avg_time_to_recovery_minutes: float | None
    median_time_to_recovery_minutes: float | None
    real_candidate_count: int
    real_execution_verified_count: int


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


def _false_actions(db: Session, actioned: list[FailedPayment]) -> list[FailedPayment]:
    """Actions ground truth says should never have been taken.

    This is deliberately not `blocked / actioned` -- that ratio only counts
    mistakes *this system's own safety monitor happened to catch*, so a wrong
    action the monitor misses is invisible to it and the number can only ever
    flatter us. Grading against `true_root_cause` instead means a miss counts
    whether or not anything downstream noticed.

    Two families, both drawn from what the card networks actually penalise:
    - any automated action on a transaction that was truly fraud;
    - any *retry* against a true hard decline (DECLINE_TYPE), which is the
      combination Visa/Mastercard fine merchants for. In practice this only
      fires when the classifier mislabels a hard decline as something
      retryable -- which is exactly the error worth surfacing.

    Webhook-ingested rows carry no ground truth and are excluded entirely
    rather than counted as either right or wrong.
    """
    retried_ids = {
        transaction_id
        for (transaction_id,) in db.query(AuditLog.transaction_id)
        .filter(
            AuditLog.event_type == "action_execution",
            AuditLog.action_taken.in_(tuple(RETRY_ACTIONS)),
        )
        .distinct()
    }

    false_actions = []
    for p in actioned:
        if p.true_root_cause == UNKNOWN_ROOT_CAUSE:
            continue
        if p.true_root_cause == "possible_fraud":
            false_actions.append(p)
        elif (
            DECLINE_TYPE.get(p.true_root_cause) == "hard"
            and p.transaction_id in retried_ids
        ):
            false_actions.append(p)

    return false_actions


def compute_summary(db: Session) -> MetricsSummary:
    payments = db.query(FailedPayment).all()
    total = len(payments)

    recovered = [p for p in payments if p.status == "recovered"]
    escalated = [p for p in payments if p.status == "escalated"]
    blocked = [p for p in payments if p.status == "blocked"]
    actioned = [p for p in payments if p.total_attempts > 0]
    gradeable_actioned = [p for p in actioned if p.true_root_cause != UNKNOWN_ROOT_CAUSE]
    false_actions = _false_actions(db, actioned)
    fraud_cases = [p for p in payments if p.true_root_cause == "possible_fraud"]
    fraud_blocked = [p for p in fraud_cases if p.status in ("escalated", "blocked")]

    recovery_times_minutes = [
        (p.resolved_at - p.failed_at).total_seconds() / 60
        for p in recovered
        if p.resolved_at is not None
    ]

    real_candidates = [p for p in payments if p.is_real]
    real_verified = [p for p in real_candidates if p.real_execution_verified]

    return MetricsSummary(
        total_transactions=total,
        total_at_risk_amount=sum(p.amount for p in payments),
        total_recovered_amount=sum(p.recovered_amount for p in recovered),
        recovery_rate=_pct(len(recovered), total),
        escalation_rate=_pct(len(escalated), total),
        blocked_rate=_pct(len(blocked), total),
        false_action_rate=_pct(len(false_actions), len(gradeable_actioned)),
        false_action_count=len(false_actions),
        safety_override_rate=_pct(len(blocked), len(actioned)),
        fraud_block_rate=_pct(len(fraud_blocked), len(fraud_cases)),
        avg_time_to_recovery_minutes=(
            round(mean(recovery_times_minutes), 2) if recovery_times_minutes else None
        ),
        median_time_to_recovery_minutes=(
            round(median(recovery_times_minutes), 2) if recovery_times_minutes else None
        ),
        real_candidate_count=len(real_candidates),
        real_execution_verified_count=len(real_verified),
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


# --- Classifier evaluation -------------------------------------------------
#
# The one metric family that grades the system against something other than
# its own behavior. Every number below compares what the classifier *said*
# (the `classification` audit event) against the generator's hidden
# `true_root_cause`, which the classifier never sees.
#
# Read with the circularity caveat stated plainly: for synthetic rows, that
# ground truth was written by the same project that wrote the classifier's
# rules, so a high rule-path accuracy is close to tautological -- the rules
# and the labels were authored together. The figures that carry real
# information are the LLM path (which was never told the mapping) and the
# calibration table, which asks a question the system cannot answer about
# itself by construction: when the classifier says it is confident, is it?

# How the raw audit `source` string collapses into a comparable path.
PATH_RULE_ENGINE = "rule_engine"
PATH_LLM = "llm"
PATH_LLM_ERROR = "llm_error"

CALIBRATION_BUCKET_COUNT = 5


@dataclass
class ClassifierPathRow:
    path: str
    total: int
    correct: int
    accuracy: float


@dataclass
class ConfusionRow:
    true_root_cause: str
    total: int
    # predicted label -> count. Includes "ambiguous", which is never a true
    # label but is what a failed/unparseable LLM call is forced to emit.
    predicted: dict[str, int] = field(default_factory=dict)


@dataclass
class CalibrationBucket:
    label: str
    lower: float
    upper: float
    total: int
    correct: int
    accuracy: float
    mean_confidence: float


@dataclass
class ClassifierMetrics:
    total_classified: int
    # Rows with usable ground truth. Webhook-ingested rows have none and are
    # excluded from every figure here rather than counted wrong.
    graded: int
    ungraded: int
    overall_accuracy: float
    paths: list[ClassifierPathRow]
    confusion: list[ConfusionRow]
    calibration: list[CalibrationBucket]
    # Does the gate the decision engine actually enforces separate right
    # answers from wrong ones? If these two accuracies are equal, the
    # threshold is doing nothing.
    confidence_threshold: float
    above_threshold_total: int
    above_threshold_accuracy: float
    below_threshold_total: int
    below_threshold_accuracy: float


def _path_of(source: str) -> str:
    if source.startswith("llm:") and source.endswith(":error"):
        return PATH_LLM_ERROR
    if source.startswith("llm:"):
        return PATH_LLM
    return PATH_RULE_ENGINE


def _calibration(graded: list[tuple[str, str, float]]) -> list[CalibrationBucket]:
    """graded is (predicted, actual, confidence). Buckets span [0,1] evenly;
    empty buckets are returned too, so the shape of the table is stable
    across runs instead of silently changing width.
    """
    width = 1 / CALIBRATION_BUCKET_COUNT
    buckets = []

    for i in range(CALIBRATION_BUCKET_COUNT):
        lower = i * width
        upper = (i + 1) * width
        # Top bucket is closed at both ends so confidence == 1.0 (every
        # rule-engine hit) lands somewhere rather than falling off the end.
        is_last = i == CALIBRATION_BUCKET_COUNT - 1

        def in_bucket(confidence: float, lower=lower, upper=upper, is_last=is_last) -> bool:
            if confidence < lower:
                return False
            return confidence <= upper if is_last else confidence < upper

        members = [
            (predicted, actual, confidence)
            for predicted, actual, confidence in graded
            if in_bucket(confidence)
        ]
        correct = sum(1 for predicted, actual, _ in members if predicted == actual)
        buckets.append(
            CalibrationBucket(
                label=f"{lower:.1f}-{upper:.1f}",
                lower=round(lower, 2),
                upper=round(upper, 2),
                total=len(members),
                correct=correct,
                accuracy=_pct(correct, len(members)),
                mean_confidence=(
                    round(mean(c for _, _, c in members), 3) if members else 0.0
                ),
            )
        )

    return buckets


def compute_classifier_metrics(db: Session) -> ClassifierMetrics:
    rows = (
        db.query(AuditLog, FailedPayment)
        .join(FailedPayment, AuditLog.transaction_id == FailedPayment.transaction_id)
        .filter(AuditLog.event_type == "classification")
        .all()
    )

    graded: list[tuple[str, str, float]] = []  # (predicted, actual, confidence)
    by_path: dict[str, list[tuple[str, str]]] = {}
    ungraded = 0

    for event, payment in rows:
        if payment.true_root_cause == UNKNOWN_ROOT_CAUSE:
            ungraded += 1
            continue

        predicted = event.root_cause or "ambiguous"
        actual = payment.true_root_cause
        graded.append((predicted, actual, event.confidence or 0.0))
        by_path.setdefault(_path_of(event.source), []).append((predicted, actual))

    correct_total = sum(1 for predicted, actual, _ in graded if predicted == actual)

    paths = []
    for path in (PATH_RULE_ENGINE, PATH_LLM, PATH_LLM_ERROR):
        members = by_path.get(path, [])
        correct = sum(1 for predicted, actual in members if predicted == actual)
        paths.append(
            ClassifierPathRow(
                path=path,
                total=len(members),
                correct=correct,
                accuracy=_pct(correct, len(members)),
            )
        )

    # Rows are the true labels the batch actually contains; columns span every
    # label the classifier can emit, so a systematic confusion (e.g. true
    # fraud predicted as gateway_timeout, the card-testing cluster) is
    # visible as a cell rather than having to be inferred from totals.
    confusion = []
    for true_root_cause in sorted({actual for _, actual, _ in graded}):
        members = [predicted for predicted, actual, _ in graded if actual == true_root_cause]
        counts = {label: members.count(label) for label in ROOT_CAUSES + ["ambiguous"]}
        confusion.append(
            ConfusionRow(
                true_root_cause=true_root_cause,
                total=len(members),
                predicted={label: n for label, n in counts.items() if n},
            )
        )

    threshold = settings.confidence_threshold
    above = [(p, a) for p, a, c in graded if c >= threshold]
    below = [(p, a) for p, a, c in graded if c < threshold]
    above_correct = sum(1 for p, a in above if p == a)
    below_correct = sum(1 for p, a in below if p == a)

    return ClassifierMetrics(
        total_classified=len(rows),
        graded=len(graded),
        ungraded=ungraded,
        overall_accuracy=_pct(correct_total, len(graded)),
        paths=paths,
        confusion=confusion,
        calibration=_calibration(graded),
        confidence_threshold=threshold,
        above_threshold_total=len(above),
        above_threshold_accuracy=_pct(above_correct, len(above)),
        below_threshold_total=len(below),
        below_threshold_accuracy=_pct(below_correct, len(below)),
    )
