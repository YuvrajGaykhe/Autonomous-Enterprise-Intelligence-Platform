"""
The open pipeline's partitions (VS-02 plan A10), and the data checks that
come before any figure (A10.5).

build_partitions takes the deal facts, a rate set, the stage vocabulary and
as_of, and divides the open valued deals four ways, each deal in exactly one
bucket of each:

    by_currency         one bucket per currency a deal holds
    by_stage            one bucket per value of the stage vocabulary, always
    by_owner            one per owning employee, then UNASSIGNED, UNRESOLVED
    by_expected_close   OVERDUE, twelve calendar months, LATER, UNDATED

It works in three stages, in this order, and a stage begins only when the
one before it has finished without error for every deal (A10.5 item 3):

    1. Data validity            the reserved-key and stage checks, over all
                                the deals; then each deal's amount and
                                currency become a MoneyValue
    2. Weighting and conversion the four per-deal values of app.pipeline.measures
    3. Aggregation              every figure a sum of per-deal values

So a data-validity error is never reported as a missing rate, whichever
deals carry the two conditions and in whatever order the facts arrive, and
no partition is returned unless every one can be.

Every list is ordered here, by Unicode code point, and the twelve months
chronologically. No order is taken from the order the facts arrive in.

This module is pure: no session, no clock, no rate set of its own loading.
It builds no count, no band cross-tabulation and no concentration. Those are
VS02-M3's; the two concentration constants below are defined now only
because the methodology digest covers them (OD-2).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, TypeVar

from app.fx.rates import RateSet
from app.intelligence.money import MoneyValue
from app.pipeline.errors import RESERVED_KEY, STAGE_OUTSIDE_VOCABULARY, PipelineDataError
from app.pipeline.facts import (
    OWNER_BASIS,
    OWNER_CARRIER_FIELD,
    DealFact,
    OwnerKind,
    ValuedDeal,
    owner_kind,
    valued_deal,
)
from app.pipeline.measures import DealValues, deal_values, total
from app.relationships import EdgeBasis

#: Plan A10.4: the expected-close window is as_of's month and the eleven after it.
PERIOD_HORIZON = 12
#: Plan A11: how many holders a concentration block lists, and the points its
#: cumulative share is stated at. Defined from VS02-M2 (OD-2); nothing reads
#: them before VS02-M3 but the methodology digest.
CONCENTRATION_TOP_N = 5
CUMULATIVE_POINTS = (1, 3, 5)

#: Plan A14.1 item 7: the names of the pseudo-buckets. One namespace, and
#: there is no second one. A bucket key taken from data or from a vocabulary
#: that equals any of them fails closed; it is never renamed or merged.
RESERVED_KEYS = frozenset({"UNASSIGNED", "UNRESOLVED", "UNLINKED", "OVERDUE", "LATER", "UNDATED",
                           "ALL", "UNASSESSED"})


class PeriodKind(StrEnum):
    """Plan A10.4: what an expected-close bucket holds."""

    OVERDUE = "OVERDUE"
    MONTH = "MONTH"
    LATER = "LATER"
    UNDATED = "UNDATED"


@dataclass(frozen=True)
class Amount:
    """Unweighted and weighted exposure in one currency. Never added to each other."""

    currency: str
    unweighted: Decimal
    weighted: Decimal


@dataclass(frozen=True)
class Bucket:
    """
    One bucket of a partition (plan A14.4).

    native holds one Amount per currency the bucket's deals hold, ascending
    and never summed. base is the one figure across them, in the rate set's
    base currency: the sum of the deals' own converted values.
    """

    key: str
    deal_count: int
    deal_ids: tuple[str, ...]
    native: tuple[Amount, ...]
    base: Amount


@dataclass(frozen=True)
class CurrencyBucket(Bucket):
    """A by_currency bucket: its key is the currency, and it states the rate applied."""

    rate_to_base: Decimal


@dataclass(frozen=True)
class OwnerBucket(Bucket):
    """A by_owner bucket: how the owner is known, and the keys that named no one."""

    kind: OwnerKind
    basis: EdgeBasis | None
    carrier_field: str | None
    unresolved_keys: tuple[str, ...]


@dataclass(frozen=True)
class PeriodBucket(Bucket):
    """A by_expected_close bucket."""

    kind: PeriodKind


@dataclass(frozen=True)
class Partitions:
    """The four partitions of the open valued deals (plan A10)."""

    by_currency: tuple[CurrencyBucket, ...]
    by_stage: tuple[Bucket, ...]
    by_owner: tuple[OwnerBucket, ...]
    by_expected_close: tuple[PeriodBucket, ...]


@dataclass(frozen=True)
class _Measured:
    """One open valued deal with its four values."""

    deal: ValuedDeal
    values: DealValues


_B = TypeVar("_B", bound=Bucket)


def build_partitions(
    facts: Iterable[DealFact],
    rate_set: RateSet,
    stage_vocabulary: Collection[str],
    as_of: date,
) -> Partitions:
    """
    The four partitions of the open valued deals, or an error and nothing.

    A closed deal and an open deal that cannot be valued sit in no bucket,
    generate no key and are checked for nothing (plan A8.3, A10.2 item 4).
    """
    valued = sorted((deal for deal in map(valued_deal, facts) if deal is not None),
                    key=_by_source_id)
    stages = sorted(set(stage_vocabulary))

    # Stage 1: data validity, for every deal, before anything is converted.
    _check_reserved_keys(valued, stages)
    _check_stages(valued, stages)
    amounts = [MoneyValue(amount=deal.amount, currency=deal.currency) for deal in valued]

    # Stage 2: weighting and conversion, per deal.
    measured = [_Measured(deal, deal_values(amount, deal.probability, rate_set))
                for deal, amount in zip(valued, amounts, strict=True)]

    # Stage 3: aggregation. Every figure is a sum of per-deal values.
    base_currency = rate_set.base_currency
    return Partitions(
        by_currency=_by_currency(measured, rate_set),
        by_stage=tuple(
            _bucket(Bucket, stage, [one for one in measured if one.deal.stage == stage],
                    base_currency)
            for stage in stages),
        by_owner=_by_owner(measured, base_currency),
        by_expected_close=_by_expected_close(measured, as_of, base_currency),
    )


def _check_reserved_keys(valued: Sequence[ValuedDeal], stages: Sequence[str]) -> None:
    """
    Plan A10.5 item 1: no generated key may equal a reserved one.

    The generated keys are every value of the stage vocabulary, whose bucket
    is always present, and the currency and the owning employee of each open
    valued deal. The currency ALL is the case plan A10.1 item 3 settles: it
    is valid Layer 1 data and it fails here, whatever the rate set holds.
    """
    collisions = [(deal.fact.source_id, key) for deal in valued for key in _generated_keys(deal)
                  if key in RESERVED_KEYS]
    keys = {stage for stage in stages if stage in RESERVED_KEYS} | {key for _, key in collisions}
    if keys:
        raise PipelineDataError(RESERVED_KEY, keys=keys,
                                source_ids={source_id for source_id, _ in collisions})


def _generated_keys(deal: ValuedDeal) -> tuple[str, ...]:
    """The bucket keys one deal's data generates: its currency and, when it has one, its owner."""
    if deal.fact.owner is None:
        return (deal.currency,)
    return (deal.currency, deal.fact.owner)


def _check_stages(valued: Sequence[ValuedDeal], stages: Sequence[str]) -> None:
    """Plan A10.2 item 4: an open valued deal's stage selects its bucket, so it must have one."""
    outside = {deal.fact.source_id for deal in valued if deal.stage not in stages}
    if outside:
        raise PipelineDataError(STAGE_OUTSIDE_VOCABULARY, source_ids=outside)


def _by_currency(measured: Sequence[_Measured], rate_set: RateSet) -> tuple[CurrencyBucket, ...]:
    """Plan A10.1: one bucket per currency a deal holds, ascending, with the rate applied."""
    return tuple(
        _bucket(CurrencyBucket, currency,
                [one for one in measured if one.deal.currency == currency],
                rate_set.base_currency, rate_to_base=rate_set.rates[currency])
        for currency in sorted({one.deal.currency for one in measured}))


def _by_owner(measured: Sequence[_Measured], base_currency: str) -> tuple[OwnerBucket, ...]:
    """
    Plan A10.3: the employees ascending, then UNASSIGNED, then UNRESOLVED.

    The last two are always present and never collapse. Ownership is not
    composed: a deal is grouped under its own owner and nothing is walked.
    """
    kinds = [(owner_kind(one.deal.fact), one) for one in measured]
    employees = sorted({owner for one in measured
                        for owner in [one.deal.fact.owner] if owner is not None})
    unresolved = [one for kind, one in kinds if kind is OwnerKind.UNRESOLVED]
    return (
        *(_bucket(OwnerBucket, employee,
                  [one for one in measured if one.deal.fact.owner == employee], base_currency,
                  kind=OwnerKind.EMPLOYEE, basis=OWNER_BASIS, carrier_field=OWNER_CARRIER_FIELD,
                  unresolved_keys=())
          for employee in employees),
        _bucket(OwnerBucket, OwnerKind.UNASSIGNED.value,
                [one for kind, one in kinds if kind is OwnerKind.UNASSIGNED], base_currency,
                kind=OwnerKind.UNASSIGNED, basis=None, carrier_field=None, unresolved_keys=()),
        _bucket(OwnerBucket, OwnerKind.UNRESOLVED.value, unresolved, base_currency,
                kind=OwnerKind.UNRESOLVED, basis=None, carrier_field=None,
                unresolved_keys=tuple(sorted({key for one in unresolved
                                              for key in [one.deal.fact.owner_source_id]
                                              if key is not None}))),
    )


def _by_expected_close(
    measured: Sequence[_Measured], as_of: date, base_currency: str
) -> tuple[PeriodBucket, ...]:
    """Plan A10.4: always fifteen buckets, the twelve months chronological."""
    months = _month_keys(as_of)
    placed = [(_period_key(one.deal.fact.expected_close_date, as_of, months), one)
              for one in measured]
    periods = [(PeriodKind.OVERDUE.value, PeriodKind.OVERDUE),
               *((month, PeriodKind.MONTH) for month in months),
               (PeriodKind.LATER.value, PeriodKind.LATER),
               (PeriodKind.UNDATED.value, PeriodKind.UNDATED)]
    return tuple(
        _bucket(PeriodBucket, key, [one for placed_key, one in placed if placed_key == key],
                base_currency, kind=kind)
        for key, kind in periods)


def _month_keys(as_of: date) -> tuple[str, ...]:
    """
    as_of's calendar month and the eleven that follow, as YYYY-MM, in order.

    Computed on (year, month) and never by constructing a date, so an as_of
    late in year 9999 yields keys in year 10000 and nothing fails.
    """
    first = as_of.year * 12 + as_of.month - 1
    return tuple(f"{index // 12:04d}-{index % 12 + 1:02d}"
                 for index in range(first, first + PERIOD_HORIZON))


def _period_key(expected: date | None, as_of: date, months: Sequence[str]) -> str:
    """
    The one expected-close bucket a deal sits in.

    A deal expected on as_of itself is in its month; one earlier in as_of's
    own month is OVERDUE.
    """
    if expected is None:
        return PeriodKind.UNDATED.value
    if expected < as_of:
        return PeriodKind.OVERDUE.value
    offset = (expected.year - as_of.year) * 12 + expected.month - as_of.month
    return months[offset] if offset < PERIOD_HORIZON else PeriodKind.LATER.value


def _bucket(
    bucket_type: type[_B], key: str, members: Sequence[_Measured], base_currency: str,
    **added: Any,
) -> _B:
    """
    One bucket over its deals. An empty one states zeros (plan A14.4).

    Each figure is the sum of the deals' own values, in one currency at a
    time: nothing is rounded here and no native total is converted.
    """
    native = tuple(
        Amount(
            currency=currency,
            unweighted=total(currency, (one.values.native_unweighted for one in members
                                        if one.deal.currency == currency)).amount,
            weighted=total(currency, (one.values.native_weighted for one in members
                                      if one.deal.currency == currency)).amount,
        )
        for currency in sorted({one.deal.currency for one in members}))
    base = Amount(
        currency=base_currency,
        unweighted=total(base_currency, (one.values.base_unweighted for one in members)).amount,
        weighted=total(base_currency, (one.values.base_weighted for one in members)).amount,
    )
    return bucket_type(key=key, deal_count=len(members),
                       deal_ids=tuple(sorted(one.deal.fact.source_id for one in members)),
                       native=native, base=base, **added)


def _by_source_id(deal: ValuedDeal) -> str:
    return deal.fact.source_id
