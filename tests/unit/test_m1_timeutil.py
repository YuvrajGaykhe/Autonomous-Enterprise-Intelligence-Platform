"""
M1 date arithmetic: UTC bucketing, closed windows, business days.

Plan A24 fixes these rules once. A milestone that bucketed a timestamp its
own way would shift a 14-day window boundary by a day and change which
customers escalate, so the rules are pinned here rather than restated later.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.intelligence.errors import ContractViolationError
from app.intelligence.timeutil import (
    business_days_between,
    closed_window,
    days_between,
    utc_date,
)

IST = timezone(timedelta(hours=5, minutes=30))


def test_a_timestamp_buckets_to_its_utc_date():
    assert utc_date(datetime(2026, 8, 27, 12, 0, tzinfo=UTC)) == date(2026, 8, 27)


def test_a_late_utc_timestamp_stays_on_its_own_utc_date():
    """23:30 UTC is the case a local-time reading would move to the next day."""
    assert utc_date(datetime(2026, 8, 27, 23, 30, tzinfo=UTC)) == date(2026, 8, 27)


def test_an_offset_timestamp_buckets_by_utc_not_by_its_own_offset():
    # 2026-08-28 04:30+05:30 is 2026-08-27 23:00Z: the UTC date is the day before.
    assert utc_date(datetime(2026, 8, 28, 4, 30, tzinfo=IST)) == date(2026, 8, 27)


def test_a_naive_timestamp_is_refused_exactly_as_layer_1_refuses_one():
    with pytest.raises(ContractViolationError, match="naive datetime"):
        utc_date(datetime(2026, 8, 27, 23, 30))


def test_days_between_counts_calendar_days_in_both_directions():
    assert days_between(date(2026, 8, 27), date(2026, 9, 18)) == 22
    assert days_between(date(2026, 9, 18), date(2026, 8, 27)) == -22
    assert days_between(date(2026, 9, 18), date(2026, 9, 18)) == 0


def test_a_closed_window_of_n_days_contains_exactly_n_dates():
    start, end = closed_window(date(2026, 8, 31), 14)

    assert (start, end) == (date(2026, 8, 18), date(2026, 8, 31))
    assert days_between(start, end) + 1 == 14


def test_a_one_day_window_is_the_day_itself():
    assert closed_window(date(2026, 9, 18), 1) == (date(2026, 9, 18), date(2026, 9, 18))


@pytest.mark.parametrize("days", [0, -1])
def test_a_window_must_span_at_least_one_day(days):
    with pytest.raises(ContractViolationError, match="at least one day"):
        closed_window(date(2026, 9, 18), days)


def test_business_days_exclude_the_weekend():
    # Friday 2026-09-18 to Monday 2026-09-21: only Monday is an elapsed business day.
    assert business_days_between(date(2026, 9, 18), date(2026, 9, 21)) == 1
    # Friday to Saturday and Friday to Sunday elapse nothing.
    assert business_days_between(date(2026, 9, 18), date(2026, 9, 19)) == 0
    assert business_days_between(date(2026, 9, 18), date(2026, 9, 20)) == 0


def test_business_days_count_a_whole_week_as_five():
    assert business_days_between(date(2026, 9, 14), date(2026, 9, 21)) == 5
    assert business_days_between(date(2026, 9, 14), date(2026, 9, 28)) == 10


def test_business_days_across_consecutive_weekdays_count_one_each():
    monday = date(2026, 9, 14)
    for offset in range(5):
        assert business_days_between(monday, monday + timedelta(days=offset)) == offset


def test_business_days_are_never_negative():
    """An as_of earlier than a ticket's creation is zero elapsed time, not a negative SLA."""
    assert business_days_between(date(2026, 9, 18), date(2026, 9, 18)) == 0
    assert business_days_between(date(2026, 9, 18), date(2026, 8, 27)) == 0


def test_business_days_match_a_brute_force_weekday_count_over_a_year():
    """The closed-form count is the thing a reviewer would count by hand."""
    start = date(2026, 1, 1)
    for offset in range(0, 366, 7):
        end = start + timedelta(days=offset)
        expected = sum(
            1
            for step in range(1, offset + 1)
            if (start + timedelta(days=step)).weekday() < 5
        )
        assert business_days_between(start, end) == expected
