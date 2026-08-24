from datetime import datetime

from app.services import retry_scheduler

DAY = 24 * 60


def test_short_delays_are_never_rescheduled():
    """A same-session gateway retry or an in-session method switch has no
    scheduling decision to make -- it must land exactly where the delay table
    put it, 3am or not.
    """
    target = datetime(2026, 3, 10, 3, 0)

    adjustment = retry_scheduler.schedule(
        target=target, action="retry_immediate", root_cause="gateway_timeout", base_delay_minutes=5
    )

    assert adjustment.scheduled_at == target
    assert adjustment.reasoning is None


def test_day_scale_attempt_is_moved_out_of_quiet_hours():
    adjustment = retry_scheduler.schedule(
        target=datetime(2026, 3, 10, 3, 30),
        action="retry_with_backoff",
        root_cause="gateway_timeout",
        base_delay_minutes=2 * DAY,
    )

    assert adjustment.scheduled_at == datetime(2026, 3, 10, 9, 0)
    assert "quiet window" in adjustment.reasoning


def test_attempt_already_outside_quiet_hours_is_left_alone():
    target = datetime(2026, 3, 10, 14, 15)

    adjustment = retry_scheduler.schedule(
        target=target,
        action="retry_with_backoff",
        root_cause="gateway_timeout",
        base_delay_minutes=2 * DAY,
    )

    assert adjustment.scheduled_at == target
    assert adjustment.reasoning is None


def test_insufficient_funds_retry_is_pulled_onto_the_salary_credit_window():
    """29 Mar is within the lookahead of 31 Mar (last day of month), so the
    retry moves onto the payday anchor rather than firing at a trough.
    """
    adjustment = retry_scheduler.schedule(
        target=datetime(2026, 3, 29, 14, 0),
        action="retry_with_backoff",
        root_cause="insufficient_funds",
        base_delay_minutes=5 * DAY,
    )

    assert adjustment.scheduled_at == datetime(2026, 3, 31, 10, 0)
    assert "salary-credit" in adjustment.reasoning


def test_payday_alignment_never_pushes_beyond_the_lookahead():
    """Mid-month is nowhere near a payday anchor -- the attempt must stay put
    rather than being pushed two weeks out past the retry envelope.
    """
    target = datetime(2026, 3, 14, 14, 0)

    adjustment = retry_scheduler.schedule(
        target=target,
        action="retry_with_backoff",
        root_cause="insufficient_funds",
        base_delay_minutes=5 * DAY,
    )

    assert adjustment.scheduled_at == target
    assert adjustment.reasoning is None


def test_payday_alignment_does_not_apply_to_other_root_causes():
    """"Wait for payday" is a claim about the customer's balance -- it is
    meaningless for a gateway timeout, so it must not fire there even on a
    date where an insufficient_funds retry would have moved.
    """
    target = datetime(2026, 3, 29, 14, 0)

    adjustment = retry_scheduler.schedule(
        target=target,
        action="retry_with_backoff",
        root_cause="gateway_timeout",
        base_delay_minutes=5 * DAY,
    )

    assert adjustment.scheduled_at == target


def test_payday_alignment_does_not_apply_to_notifications():
    """A reminder is not a re-attempt against a balance, so only quiet hours
    govern its timing.
    """
    target = datetime(2026, 3, 29, 14, 0)

    adjustment = retry_scheduler.schedule(
        target=target,
        action="send_reminder",
        root_cause="insufficient_funds",
        base_delay_minutes=1 * DAY,
    )

    assert adjustment.scheduled_at == target


def test_first_of_month_is_also_a_payday_anchor():
    adjustment = retry_scheduler.schedule(
        target=datetime(2026, 4, 1, 4, 0),
        action="retry_with_backoff",
        root_cause="insufficient_funds",
        base_delay_minutes=5 * DAY,
    )

    # Payday alignment runs first and sets 10:00, which is already clear of
    # the quiet window -- so exactly one adjustment should be reported.
    assert adjustment.scheduled_at == datetime(2026, 4, 1, 10, 0)
    assert "salary-credit" in adjustment.reasoning
    assert "quiet window" not in adjustment.reasoning
