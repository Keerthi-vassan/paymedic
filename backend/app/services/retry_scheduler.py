"""Picks *when* a scheduled recovery attempt should land, as distinct from
*how long* to wait between attempts (executor.resolution_delay_minutes, which
only sets the day-scale spacing).

Retry count is not the only lever a real recovery system has -- retry
*timing* is the other one, and it is not cosmetic. Authorization success
rates swing by roughly 15% depending on the time of day and day of week an
attempt is made, which is why Stripe's Smart Retries and Razorpay's own
Intelligent Payment Retry are fundamentally about choosing the moment, not
just the count. A fixed (action, attempt_number) delay table alone always
lands an attempt at whatever arbitrary clock time the original failure
happened to occur at, including 3am.

Two adjustments are applied, in this order, and only to day-scale attempts
(anything spaced a day or more out -- a genuine same-session
`retry_immediate` or an in-session `suggest_alternate_method` is left
exactly where it is, since there's no scheduling decision to make there):

1. **Payday alignment**, retries on `insufficient_funds` only. This is the
   single largest failure bucket in the industry (~34% of failed recurring
   payments) and the most time-recoverable one, for a specific reason:
   nothing about the customer's *intent* failed, their balance was simply
   short at that moment, and balances refill on salary credit. If the
   scheduled attempt already lands within a few days before a payday
   anchor, it is moved forward onto that anchor rather than firing into a
   trough. Bounded by `payday_lookahead_days` so this can only ever nudge
   an attempt, never push it weeks out past the 10-14 day retry envelope.

2. **Quiet-hours avoidance**, every day-scale attempt. An attempt landing
   in the small hours is moved to the following morning. Issuer-side
   systems batch maintenance overnight, and for customer-facing actions
   (`send_reminder`) a 3am notification is simply less likely to be acted
   on than a 9am one.

Both anchors are naive local merchant time, consistent with how
`failed_at` is stored everywhere else in this project. Both are documented
assumptions about *when* to act -- they deliberately do not touch
executor.SUCCESS_PROBABILITIES, which remains the (separately documented)
assumption about whether an attempt succeeds. Nothing here changes how many
attempts are permitted; the stopping rules in decision_engine remain the
sole authority on that.
"""

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import settings
from app.services.decision_engine import RETRY_ACTIONS

# Only attempts spaced at least this far out are scheduled at all. Below it,
# the attempt is a same-session continuation of the original checkout (a
# gateway retry, or the customer picking another method while still on the
# page) -- there is no "when should this land" question to answer.
MIN_SCHEDULABLE_DELAY_MINUTES = 24 * 60

# Payday alignment applies to retries only (decision_engine.RETRY_ACTIONS),
# not notifications: it is a claim about the customer's *balance* having
# refilled, which only matters when the system is re-attempting the charge
# itself. A reminder's timing is governed by quiet hours alone.

# Root causes whose recovery odds genuinely move with salary credit. Kept
# explicit rather than applied to every cause, since "wait for payday" is a
# meaningless adjustment for a gateway timeout or a dropped connection.
PAYDAY_SENSITIVE_ROOT_CAUSES = frozenset({"insufficient_funds"})


@dataclass
class ScheduleAdjustment:
    scheduled_at: datetime
    # None when the attempt was left exactly where the delay table put it --
    # the audit trail should say nothing rather than claim a non-adjustment.
    reasoning: str | None


def _is_payday_anchor(moment: datetime) -> bool:
    """Salary in India is typically credited either on the 1st or on the last
    working day of the month. The last *calendar* day is used as the anchor
    rather than the last working day -- a weekend credit lands in the account
    by the 1st either way, so both anchors point at the same refilled balance.
    """
    last_day = calendar.monthrange(moment.year, moment.month)[1]
    return moment.day == 1 or moment.day == last_day


def _next_payday_anchor(target: datetime, lookahead_days: int) -> datetime | None:
    for offset in range(lookahead_days + 1):
        candidate = target + timedelta(days=offset)
        if _is_payday_anchor(candidate):
            return candidate.replace(
                hour=settings.payday_retry_hour, minute=0, second=0, microsecond=0
            )
    return None


def _in_quiet_hours(moment: datetime) -> bool:
    return settings.quiet_hours_start <= moment.hour < settings.quiet_hours_end


def schedule(
    target: datetime,
    action: str,
    root_cause: str,
    base_delay_minutes: float,
) -> ScheduleAdjustment:
    """`target` is where the raw delay table put this attempt. Returns where it
    should actually land, plus a human-readable reason whenever that differs.
    """
    if base_delay_minutes < MIN_SCHEDULABLE_DELAY_MINUTES:
        return ScheduleAdjustment(scheduled_at=target, reasoning=None)

    scheduled_at = target
    reasons: list[str] = []

    if action in RETRY_ACTIONS and root_cause in PAYDAY_SENSITIVE_ROOT_CAUSES:
        anchor = _next_payday_anchor(scheduled_at, settings.payday_lookahead_days)
        if anchor is not None and anchor > scheduled_at:
            reasons.append(
                f"moved from {scheduled_at:%Y-%m-%d %H:%M} to the {anchor:%d %b} salary-credit "
                f"window (within {settings.payday_lookahead_days} days) -- {root_cause} recovers "
                "on balance refill, not on repetition"
            )
            scheduled_at = anchor

    if _in_quiet_hours(scheduled_at):
        resumed = scheduled_at.replace(
            hour=settings.quiet_hours_resume_hour, minute=0, second=0, microsecond=0
        )
        reasons.append(
            f"shifted out of the {settings.quiet_hours_start:02d}:00-"
            f"{settings.quiet_hours_end:02d}:00 quiet window to "
            f"{resumed:%H:%M} -- authorization success rates vary by roughly 15% "
            "with time of day"
        )
        scheduled_at = resumed

    if not reasons:
        return ScheduleAdjustment(scheduled_at=scheduled_at, reasoning=None)

    return ScheduleAdjustment(
        scheduled_at=scheduled_at,
        reasoning="retry timing: " + "; ".join(reasons),
    )
