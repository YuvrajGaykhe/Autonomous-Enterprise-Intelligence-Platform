"""
Deterministic date arithmetic for Layer 2 (plan A24).

Three rules, fixed here so no later milestone can bucket a timestamp its
own way:

    UTC bucketing     A canonical timestamp belongs to the UTC date of
                      created_at.astimezone(UTC).date(). Naive datetimes are
                      rejected, exactly as Layer 1's record_hash rejects them.
    Closed windows    A window of n days ending on d is the closed interval
                      [d - (n - 1), d], so it contains exactly n UTC dates.
    Business days     Monday to Friday, with no holiday calendar. That is a
                      stated limitation (plan A29), not an oversight: a
                      holiday calendar is jurisdictional data the project
                      does not hold, and inventing one would make the SLA
                      arithmetic unreproducible.

Nothing here reads a clock. app/intelligence must never call datetime.now,
date.today or utcnow, and a boundary test enforces that mechanically: an
assessment is a pure function of its scope, and a clock would make two runs
of the same scope disagree.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.intelligence.errors import ContractViolationError

#: Weekdays counted as business days: Monday (0) through Friday (4).
BUSINESS_WEEKDAYS = 5


def utc_date(moment: datetime) -> date:
    """The UTC date a timezone-aware timestamp falls on."""
    if moment.utcoffset() is None:
        raise ContractViolationError(f"naive datetime {moment.isoformat()} cannot be bucketed")
    return moment.astimezone(UTC).date()


def days_between(start: date, end: date) -> int:
    """Calendar days from start to end. Negative when end precedes start."""
    return (end - start).days


def closed_window(end: date, days: int) -> tuple[date, date]:
    """The closed interval of `days` UTC dates ending on `end`."""
    if days < 1:
        raise ContractViolationError(f"a window must span at least one day, got {days}")
    return end - timedelta(days=days - 1), end


def business_days_between(start: date, end: date) -> int:
    """
    Elapsed business days in the half-open interval (start, end].

    The start date is the day the clock starts, so it is not itself elapsed;
    the end date is. A ticket created on a Friday and resolved on the
    following Monday has elapsed one business day. Never negative: an end
    before the start is zero elapsed time, which is what an as_of earlier
    than a ticket's creation means.
    """
    if end <= start:
        return 0
    return _business_days_to(end) - _business_days_to(start)


def _business_days_to(day: date) -> int:
    """Business days from the start of the proleptic Gregorian calendar to `day`."""
    # Ordinal 1 is 0001-01-01, a Monday, so whole weeks contribute five days
    # each and the remainder contributes at most five.
    ordinal = day.toordinal()
    return BUSINESS_WEEKDAYS * (ordinal // 7) + min(ordinal % 7, BUSINESS_WEEKDAYS)
