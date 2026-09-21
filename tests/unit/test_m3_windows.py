"""
M3 sliding windows and the recency lookback.

Two things are pinned here rather than left to the signal engine's tests,
because both were defects before they were rules: a window is a *closed*
interval of UTC dates, so "14 days" means fourteen dates and not thirteen
plus a boundary argument; and the lookback exists so that a burst in
January cannot escalate a customer in September.

The measured window for CUST-007 is asserted directly, because the plan
quotes it: 2026-08-18 to 2026-08-31, five tickets. Its end lies four days
past the last ticket, which is the property that catches an implementation
anchoring windows on their last member instead of their first.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.intelligence.errors import ContractViolationError
from app.intelligence.windows import (
    WindowCount,
    dates_in_lookback,
    lookback_window,
    max_window,
    sliding_windows,
)

AS_OF = date(2026, 9, 18)
LOOKBACK = 90
WINDOW = 14

#: The five CUST-007 ticket dates the plan measures (TKT-073/075/076/079/080).
MERIDIAN = (
    date(2026, 8, 18), date(2026, 8, 20), date(2026, 8, 23),
    date(2026, 8, 25), date(2026, 8, 27),
)


def windows(dates, as_of=AS_OF, *, window_days=WINDOW, lookback_days=LOOKBACK):
    return sliding_windows(dates, as_of, window_days=window_days, lookback_days=lookback_days)


def largest(dates, as_of=AS_OF, *, window_days=WINDOW, lookback_days=LOOKBACK):
    return max_window(dates, as_of, window_days=window_days, lookback_days=lookback_days)


# ---------------------------------------------------------------------------
# WindowCount
# ---------------------------------------------------------------------------


def test_a_window_spans_a_closed_interval_of_dates():
    """Fourteen days means fourteen dates, not thirteen plus an argument."""
    window = WindowCount(start=date(2026, 8, 18), end=date(2026, 8, 31), count=5)

    assert window.days == WINDOW


def test_a_single_day_window_spans_one_day():
    assert WindowCount(start=AS_OF, end=AS_OF, count=0).days == 1


def test_a_window_cannot_end_before_it_starts():
    with pytest.raises(ContractViolationError, match="cannot end before it starts"):
        WindowCount(start=date(2026, 8, 31), end=date(2026, 8, 18), count=1)


def test_a_window_count_cannot_be_negative():
    with pytest.raises(ContractViolationError, match="cannot be negative"):
        WindowCount(start=AS_OF, end=AS_OF, count=-1)


def test_a_window_projects_dates_and_a_count_and_no_timestamp():
    payload = WindowCount(start=date(2026, 8, 18), end=date(2026, 8, 31), count=5).to_payload()

    assert payload == {"start": "2026-08-18", "end": "2026-08-31", "count": 5}


# ---------------------------------------------------------------------------
# The lookback
# ---------------------------------------------------------------------------


def test_the_lookback_is_a_closed_interval_ending_at_as_of():
    start, end = lookback_window(AS_OF, LOOKBACK)

    assert end == AS_OF
    assert (end - start).days + 1 == LOOKBACK


def test_a_date_older_than_the_lookback_is_not_visible():
    """Strategy 4.4: a January burst must not escalate a customer in September."""
    start, _ = lookback_window(AS_OF, LOOKBACK)
    january = date(2026, 1, 17)

    assert dates_in_lookback([january], AS_OF, LOOKBACK) == ()
    assert january < start


def test_a_date_after_as_of_is_not_yet_visible():
    """An assessment states the position on its evaluation date, not after it."""
    tomorrow = AS_OF + timedelta(days=1)

    assert dates_in_lookback([AS_OF, tomorrow], AS_OF, LOOKBACK) == (AS_OF,)


def test_the_lookback_keeps_duplicates_and_returns_them_in_order():
    day = date(2026, 9, 1)

    assert dates_in_lookback([day, date(2026, 8, 20), day], AS_OF, LOOKBACK) == (
        date(2026, 8, 20), day, day,
    )


def test_the_first_and_last_dates_of_the_lookback_are_both_inside_it():
    start, end = lookback_window(AS_OF, LOOKBACK)

    assert dates_in_lookback([start, end], AS_OF, LOOKBACK) == (start, end)


# ---------------------------------------------------------------------------
# Sliding windows
# ---------------------------------------------------------------------------


def test_a_window_must_span_at_least_one_day():
    with pytest.raises(ContractViolationError, match="at least one day"):
        windows(MERIDIAN, window_days=0)


def test_there_is_one_window_per_distinct_date_in_the_lookback():
    assert len(windows(MERIDIAN)) == len(set(MERIDIAN))


def test_two_tickets_on_one_day_share_one_window_and_are_both_counted():
    day = date(2026, 9, 1)

    assert windows([day, day]) == (WindowCount(start=day, end=date(2026, 9, 14), count=2),)


def test_an_empty_lookback_yields_no_window():
    assert windows([date(2026, 1, 17)]) == ()


def test_a_window_is_clipped_at_as_of_rather_than_dropped():
    """A burst still in progress must not vanish because its window runs past today."""
    yesterday = date(2026, 9, 17)

    assert windows([yesterday, AS_OF]) == (
        WindowCount(start=yesterday, end=AS_OF, count=2),
        WindowCount(start=AS_OF, end=AS_OF, count=1),
    )


def test_a_window_does_not_count_a_ticket_older_than_the_lookback():
    """A window reaching back over the lookback edge must not drag a ticket in."""
    start, _ = lookback_window(AS_OF, LOOKBACK)
    just_outside = start - timedelta(days=1)

    assert windows([just_outside, start]) == (
        WindowCount(start=start, end=start + timedelta(days=WINDOW - 1), count=1),
    )


@pytest.mark.parametrize("window_days, expected", [(13, 1), (14, 2), (15, 2)])
def test_the_window_boundary_decides_whether_a_pair_falls_together(window_days, expected):
    """
    Two tickets exactly thirteen days apart.

    A 14-day closed window holds both: it spans the start date and the
    thirteen after it. A 13-day window holds only the first. This is the
    boundary an off-by-one turns into a wrong escalation state.
    """
    first = date(2026, 8, 18)
    second = date(2026, 8, 31)

    assert largest([first, second], window_days=window_days).count == expected


# ---------------------------------------------------------------------------
# The fullest window
# ---------------------------------------------------------------------------


def test_the_fullest_window_for_meridian_is_the_one_the_plan_measured():
    assert largest(MERIDIAN) == WindowCount(
        start=date(2026, 8, 18), end=date(2026, 8, 31), count=5
    )


def test_the_fullest_window_ends_past_the_last_ticket():
    """A window is anchored where it starts, not where its last member falls."""
    assert largest(MERIDIAN).end > max(MERIDIAN)


def test_there_is_no_fullest_window_when_the_lookback_is_empty():
    assert largest([]) is None
    assert largest([date(2026, 1, 17)]) is None


def test_a_tie_breaks_on_the_earliest_start():
    """
    Two isolated tickets, far enough apart that each anchors its own window.

    Both windows hold exactly one ticket, so the counts genuinely tie and
    the tiebreak is the only thing deciding the answer. Dates close enough
    to share a window would not tie, and would let a reversed tiebreak pass.
    """
    early = date(2026, 7, 1)
    late = date(2026, 9, 1)
    both = largest([early, late])

    assert [window.count for window in windows([early, late])] == [1, 1]
    assert both.start == early
    assert largest([late, early]) == both


def test_the_fullest_window_does_not_depend_on_the_order_the_dates_arrive_in():
    shuffled = [MERIDIAN[3], MERIDIAN[0], MERIDIAN[4], MERIDIAN[1], MERIDIAN[2]]

    assert largest(shuffled) == largest(MERIDIAN)


def test_the_fullest_window_falls_below_the_threshold_once_the_lookback_excludes_it():
    """The same five tickets, evaluated far enough later, escalate nobody."""
    much_later = date(2027, 6, 1)

    assert largest(MERIDIAN, much_later) is None
