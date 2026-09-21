"""
The sliding window and the recency lookback (VS-01 M3).

Two measured traps shape this module, and both are about *time* rather than
about counting:

    The lookback     DOC-003 escalates a customer who raises three or more
                     tickets within 14 days. Applied to all history, that
                     escalates a customer forever on the strength of a burst
                     in January. Strategy section 4.4 therefore constrains
                     the rule to a recency window ending at as_of, and this
                     module is where that constraint is applied rather than
                     remembered.
    The window end   A 14-day window is a closed interval of 14 UTC dates
                     (plan A24). The measured window for CUST-007 is
                     2026-08-18 to 2026-08-31 - its end lies four days past
                     the last ticket, because a window is anchored to where
                     it starts, not to where its last ticket happens to fall.

Candidate windows are anchored on ticket dates. A window holding the most
tickets can always be slid until it starts on one of them, so enumerating
the ticket-anchored windows finds the maximum without enumerating every
date. A window whose end would run past as_of is clipped to as_of: no
ticket can exist after the evaluation date, so clipping changes no count,
and dropping such a window instead would undercount a burst that is still
in progress.

Nothing here reads a clock or a database. Every function is a pure function
of the dates it is given.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.intelligence.errors import ContractViolationError
from app.intelligence.timeutil import closed_window


@dataclass(frozen=True)
class WindowCount:
    """A closed interval of UTC dates and how many tickets fall inside it."""

    start: date
    end: date
    count: int

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ContractViolationError(
                f"a window cannot end before it starts: [{self.start}, {self.end}]"
            )
        if self.count < 0:
            raise ContractViolationError(f"a window count cannot be negative: {self.count}")

    @property
    def days(self) -> int:
        """Dates in the closed interval, so a one-day window spans one day."""
        return (self.end - self.start).days + 1

    def to_payload(self) -> dict[str, object]:
        """Deterministic projection. Carries no timestamp."""
        return {"start": self.start.isoformat(), "end": self.end.isoformat(),
                "count": self.count}


def lookback_window(as_of: date, lookback_days: int) -> tuple[date, date]:
    """The closed interval of `lookback_days` UTC dates ending at as_of."""
    return closed_window(as_of, lookback_days)


def dates_in_lookback(
    dates: Iterable[date], as_of: date, lookback_days: int
) -> tuple[date, ...]:
    """
    The given dates that fall inside the lookback window, in ascending order.

    Dates after as_of are excluded here rather than by every caller: an
    assessment is computed as of a date, so a row created after it is not
    yet visible to the assessment that names it.
    """
    start, end = lookback_window(as_of, lookback_days)
    return tuple(sorted(day for day in dates if start <= day <= end))


def sliding_windows(
    dates: Sequence[date], as_of: date, *, window_days: int, lookback_days: int
) -> tuple[WindowCount, ...]:
    """
    Every ticket-anchored window in the lookback, ordered by start date.

    One window per distinct date in the lookback, running `window_days` dates
    forward from it and clipped at as_of. Counts are taken over the same
    lookback-restricted dates, so a ticket older than the lookback is never
    counted by a window that merely reaches back over it.
    """
    if window_days < 1:
        raise ContractViolationError(
            f"a window must span at least one day, got {window_days}"
        )
    visible = dates_in_lookback(dates, as_of, lookback_days)
    windows = []
    for anchor in sorted(set(visible)):
        end = min(anchor + timedelta(days=window_days - 1), as_of)
        count = sum(1 for day in visible if anchor <= day <= end)
        windows.append(WindowCount(start=anchor, end=end, count=count))
    return tuple(windows)


def max_window(
    dates: Sequence[date], as_of: date, *, window_days: int, lookback_days: int
) -> WindowCount | None:
    """
    The fullest ticket-anchored window, or None when the lookback is empty.

    Ties break on the earliest start, so the answer does not depend on the
    order the dates arrived in. Reporting the window rather than only its
    count is what lets a brief say *which* nine days the burst happened in.
    """
    windows = sliding_windows(
        dates, as_of, window_days=window_days, lookback_days=lookback_days
    )
    if not windows:
        return None
    return max(windows, key=lambda window: (window.count, -window.start.toordinal()))
