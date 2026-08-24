"""Root-cause classification: deterministic rules first, LLM fallback for the
rest. Fraud is always decided by the risk_score rule below -- it is never
delegated to the LLM, since it's the one safety-critical branch. The LLM
provider is swappable (see app/services/llm/) and, like the rules, only ever
emits a label -- it never decides or executes a recovery action itself.
"""

from collections import Counter
from dataclasses import dataclass

from app.config import settings
from app.models import FailedPayment
from app.services import llm

ERROR_REASON_TO_ROOT_CAUSE = {
    "insufficient_funds": "insufficient_funds",
    "low_balance": "insufficient_funds",
    "gateway_timeout_error": "gateway_timeout",
    "gateway_technical_error": "gateway_timeout",
    "bank_technical_error": "gateway_timeout",
    "incorrect_otp": "auth_failure",
    "authentication_failed": "auth_failure",
    "otp_timeout": "auth_failure",
    "connection_timeout": "network_drop",
    "customer_connection_break": "network_drop",
    "issuer_declined": "card_declined",
    "do_not_honor": "card_declined",
    "card_declined": "card_declined",
}

AMBIGUOUS_ROOT_CAUSE = "ambiguous"


@dataclass
class ClassificationResult:
    root_cause: str
    confidence: float
    reasoning: str
    source: str  # rule_engine | llm:<provider> | llm:<provider>:error


def classify(payment: FailedPayment) -> ClassificationResult:
    if payment.risk_score >= settings.fraud_risk_score_threshold:
        return ClassificationResult(
            root_cause="possible_fraud",
            confidence=1.0,
            reasoning=(
                f"risk_score {payment.risk_score:.2f} >= fraud threshold "
                f"{settings.fraud_risk_score_threshold:.2f} -- rule-based fraud flag"
            ),
            source="rule_engine",
        )

    if payment.error_reason in ERROR_REASON_TO_ROOT_CAUSE:
        root_cause = ERROR_REASON_TO_ROOT_CAUSE[payment.error_reason]
        return ClassificationResult(
            root_cause=root_cause,
            confidence=0.95,
            reasoning=f"error_reason '{payment.error_reason}' maps deterministically to {root_cause}",
            source="rule_engine",
        )

    # No deterministic rule matched -- ask the LLM, more than once, and use
    # how much it agrees with itself as the confidence (see _classify_by_
    # consensus). A failed/unreachable call falls back to the same safe
    # "ambiguous, zero confidence" shape a malformed response would, so the
    # decision engine escalates for human review rather than silently
    # skipping or misclassifying the transaction.
    return _classify_by_consensus(payment)


def _classify_by_consensus(payment: FailedPayment) -> ClassificationResult:
    """Sample the classification `classification_samples` times and score it by
    self-consistency rather than by the model's own claim about itself.

    A model asked "how confident are you?" just writes a number, and that
    number is a poor predictor of whether it is actually right -- roughly
    0.627 AUROC in published evaluations, barely above the 0.5 of a coin
    flip. Whether independent samples *agree with each other* is a
    substantially stronger signal (0.65-0.74), needs no logprobs, no special
    model access, and no training -- only running the same call more than
    once. That is the entire technique.

    The reported confidence is the **more pessimistic** of the two signals:

        confidence = min(agreement, mean self-report among the winning votes)

    so neither can inflate the other. Unanimous-but-hesitant stays low;
    emphatic-but-inconsistent also stays low. Only agreement *and* stated
    confidence together clear the gate. This can lower a confidence relative
    to the old single-sample behaviour but never raise it, which keeps the
    change safe in the same direction as everything else here.

    Ties escalate for free: with 3 samples and 3 different answers, agreement
    is 0.33; with 4 samples split 2-2 it is 0.5. Both fall under the 0.6
    threshold, so a genuinely torn classifier goes to a human without needing
    a special case.

    `classification_samples = 1` reproduces the previous behaviour exactly
    (agreement is trivially 1.0, so confidence collapses to the self-reported
    number), which is what makes an honest before/after comparison possible
    on the same batch via /metrics/classifier.

    **This depends on the provider sampling non-deterministically.** All four
    adapters use their provider's default temperature, which is non-zero for
    every one of them. Pinning temperature to 0 would make every sample
    identical, agreement trivially 1.0, and this measurement meaningless.

    Samples are taken sequentially rather than in parallel: pipeline.run_batch
    already parallelises across transactions, and fanning out here too would
    multiply total concurrency into provider per-minute rate limits.
    """
    provider = llm.get_provider()
    samples: list[llm.LLMClassification] = []
    failures: list[str] = []

    for _ in range(max(1, settings.classification_samples)):
        try:
            samples.append(provider.classify_ambiguous(payment))
        except Exception as exc:
            failures.append(str(exc))

    if not samples:
        return ClassificationResult(
            root_cause=AMBIGUOUS_ROOT_CAUSE,
            confidence=0.0,
            reasoning=f"all {len(failures)} LLM sample(s) failed ({failures[0]}) -- escalating for human review",
            source=f"llm:{provider.name}:error",
        )

    votes = Counter(sample.root_cause for sample in samples)
    winner, winner_count = votes.most_common(1)[0]
    agreement = winner_count / len(samples)

    # Averaged over the winning votes only -- averaging across samples that
    # disagreed about the label would blend confidences for different answers.
    winning_samples = [s for s in samples if s.root_cause == winner]
    mean_self_reported = sum(s.confidence for s in winning_samples) / len(winning_samples)
    confidence = round(min(agreement, mean_self_reported), 4)

    vote_summary = ", ".join(f"{cause} x{n}" for cause, n in votes.most_common())
    reasoning = (
        f"{winner_count}/{len(samples)} samples agreed on {winner} ({vote_summary}); "
        f"confidence = min(agreement {agreement:.2f}, mean self-reported "
        f"{mean_self_reported:.2f}) = {confidence:.2f}. "
        f"Majority sample's reasoning: {winning_samples[0].reasoning}"
    )
    if failures:
        reasoning += f" [{len(failures)} sample(s) failed and were excluded]"

    return ClassificationResult(
        root_cause=winner,
        confidence=confidence,
        reasoning=reasoning,
        source=f"llm:{provider.name}",
    )
