"""
The open pipeline's partitions (VS-02 plan A10, A12), the data checks that
come before any figure (A10.5), and concentration and coincidence (A11,
A12.5).

build_partitions takes the deal facts, a rate set, the stage vocabulary and
as_of, and from VS02-M3 the bands VS-01 persisted. It divides the open
valued deals six ways, each deal in exactly one bucket of each:

    by_currency         one bucket per currency a deal holds
    by_stage            one bucket per value of the stage vocabulary, always
    by_owner            one per owning employee, then UNASSIGNED, UNRESOLVED
    by_expected_close   OVERDUE, twelve calendar months, LATER, UNDATED
    by_risk_band        the four bands by descending rank, then UNASSESSED
                        and UNLINKED, always (M3)
    by_customer         one per customer holding a deal, by exposure, then
                        UNLINKED, always (M3)

It works in three stages, in this order, and a stage begins only when the
one before it has finished without error for every deal (A10.5 item 3):

    1. Data validity            the reserved-key and stage checks, over all
                                the deals; then each deal's amount and
                                currency become a MoneyValue
    2. Weighting and conversion the four per-deal values of app.pipeline.measures
    3. Aggregation              every figure a sum of per-deal values

So a data-validity error is never reported as a missing rate, whichever
deals carry the two conditions and in whatever order the facts arrive, and
no partition is returned unless every one can be. The stored bands are held
against the frozen vocabulary after stage 1 and before anything is
converted. valid_deals is stage 1 by itself, for the caller that must run
it ahead of a check of its own (plan A17.1, OD-M3-1); build_partitions runs
the same function.

A band only selects the bucket a deal's amounts are summed in. No amount is
multiplied, discounted or weighted by one, and where a band and an amount
both order a list the order is lexicographic: band rank, then exposure, then
id (A12.4).

Concentration is structure here and arithmetic elsewhere (OD-M3-6). This
module decides which buckets are holders, their order, the top and the
cumulative points, and the zero form. Every division, square and rounding
is app.pipeline.measures': nothing here rounds, and the arithmetic context
is not imported.

Every list is ordered here, by Unicode code point, and the twelve months
chronologically. No order is taken from the order the facts arrive in.

This module is pure: no session, no clock, no rate set of its own loading.
It builds no count: deal_counts is the view's (OD-4).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, TypeVar

from app.fx.rates import RateSet
from app.intelligence.contract import RiskBand
from app.intelligence.money import MoneyValue
from app.pipeline.errors import RESERVED_KEY, STAGE_OUTSIDE_VOCABULARY, PipelineDataError
from app.pipeline.facts import (
    OWNER_BASIS,
    OWNER_CARRIER_FIELD,
    BandFact,
    CustomerBand,
    DealFact,
    OwnerKind,
    ValuedDeal,
    customer_bands,
    owner_kind,
    valued_deal,
)
from app.pipeline.measures import DealValues, cumulative_share, deal_values, hhi, share, total
from app.relationships import EdgeBasis

#: Plan A10.4: the expected-close window is as_of's month and the eleven after it.
PERIOD_HORIZON = 12
#: Plan A11: how many holders a concentration block lists, and the points its
#: cumulative share is stated at. Defined from VS02-M2 (OD-2), because the
#: methodology digest covers them, and read by concentration from VS02-M3.
CONCENTRATION_TOP_N = 5
CUMULATIVE_POINTS = (1, 3, 5)

#: Plan A14.1 item 7: the names of the pseudo-buckets. One namespace, and
#: there is no second one. A bucket key taken from data or from a vocabulary
#: that equals any of them fails closed; it is never renamed or merged.
RESERVED_KEYS = frozenset({"UNASSIGNED", "UNRESOLVED", "UNLINKED", "OVERDUE", "LATER", "UNDATED",
                           "ALL", "UNASSESSED"})
#: Plan A14.2: the key of the one bucket over every open valued deal. It is
#: a reserved key, and it is also an ISO 4217 code Layer 1 admits (OD-8), so
#: it is written here and in the reserved keys and nowhere else.
OPEN_PIPELINE_KEY = "ALL"
#: Plan A12.3: the two coverage buckets of the band partition. A customer
#: with no assessment at the identity is UNASSESSED, and never NONE; a deal
#: with no customer is UNLINKED.
UNASSESSED = "UNASSESSED"
UNLINKED = "UNLINKED"
#: Plan A11 item 6: why a concentration block states no share.
NO_OPEN_EXPOSURE = "NO_OPEN_EXPOSURE"


class PeriodKind(StrEnum):
    """Plan A10.4: what an expected-close bucket holds."""

    OVERDUE = "OVERDUE"
    MONTH = "MONTH"
    LATER = "LATER"
    UNDATED = "UNDATED"


class CustomerKind(StrEnum):
    """Plan A12.6: what a by_customer bucket holds."""

    CUSTOMER = "CUSTOMER"
    UNLINKED = "UNLINKED"


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
class BandBucket(Bucket):
    """A by_risk_band bucket: the customers whose deals it holds, ascending."""

    customer_count: int
    customer_ids: tuple[str, ...]


@dataclass(frozen=True)
class CustomerBucket(Bucket):
    """
    A by_customer bucket: the customer's stored band and verdict beside its exposure.

    band is a value of the frozen vocabulary, or UNASSESSED when the customer
    has no assessment at the identity. It and the verdict are None for the
    UNLINKED bucket, and the verdict is None wherever there is no assessment.
    """

    kind: CustomerKind
    band: str | None
    executive_worthy: bool | None


@dataclass(frozen=True)
class Holder:
    """One of a concentration block's largest holders (plan A11 item 5)."""

    key: str
    pseudo: bool
    amount: Decimal
    share: Decimal


@dataclass(frozen=True)
class CumulativeShare:
    """The share the largest `holders` holders have together, or all of them when fewer."""

    holders: int
    share: Decimal


@dataclass(frozen=True)
class Concentration:
    """
    How concentrated one measure of open exposure is over one partition (plan A14.7).

    Always in the rate set's base currency, and it names the rate set it was
    converted under: a share moves with the rates.
    """

    currency: str
    rate_set_version: str
    total: Decimal
    holder_count: int
    top: tuple[Holder, ...]
    cumulative: tuple[CumulativeShare, ...]
    hhi: Decimal | None
    reason: str | None


@dataclass(frozen=True)
class ConcentrationPair:
    """One partition's two blocks. The measures are never added to each other."""

    unweighted: Concentration
    weighted: Concentration


@dataclass(frozen=True)
class Concentrations:
    """The four concentration blocks (plan A11 item 3)."""

    by_customer: ConcentrationPair
    by_owner: ConcentrationPair


@dataclass(frozen=True)
class Partitions:
    """
    The partitions of the open valued deals (plan A10, A12), and what is read off them.

    The first four are VS02-M2's and are what they were. VS02-M3 adds the
    band and customer partitions, the bucket over every deal, coincidence,
    concentration, and each deal's own four values, which the view states.
    """

    by_currency: tuple[CurrencyBucket, ...]
    by_stage: tuple[Bucket, ...]
    by_owner: tuple[OwnerBucket, ...]
    by_expected_close: tuple[PeriodBucket, ...]
    open_pipeline: Bucket
    by_risk_band: tuple[BandBucket, ...]
    by_customer: tuple[CustomerBucket, ...]
    risk_coincidence: tuple[str, ...]
    concentration: Concentrations
    per_deal: tuple[tuple[str, DealValues], ...]


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
    bands: Iterable[BandFact] = (),
) -> Partitions:
    """
    The partitions of the open valued deals, or an error and nothing.

    A closed deal and an open deal that cannot be valued sit in no bucket,
    generate no key and are checked for nothing (plan A8.3, A10.2 item 4).
    With no band supplied every linked deal is UNASSESSED: missing coverage
    is a bucket, not an error (plan A12.3 item 4).
    """
    stages = sorted(set(stage_vocabulary))

    # Stage 1: data validity, for every deal, before anything is converted.
    valid = valid_deals(facts, stages)
    # The stored bands, each held against the frozen vocabulary (plan A12.3 item 2).
    assessed = customer_bands(bands)

    # Stage 2: weighting and conversion, per deal.
    measured = [_Measured(deal, deal_values(amount, deal.probability, rate_set))
                for deal, amount in valid]

    # Stage 3: aggregation. Every figure is a sum of per-deal values.
    base_currency = rate_set.base_currency
    open_pipeline = _bucket(Bucket, OPEN_PIPELINE_KEY, measured, base_currency)
    by_owner = _by_owner(measured, base_currency)
    by_customer = _by_customer(measured, base_currency, assessed)
    return Partitions(
        by_currency=_by_currency(measured, rate_set),
        by_stage=tuple(
            _bucket(Bucket, stage, [one for one in measured if one.deal.stage == stage],
                    base_currency)
            for stage in stages),
        by_owner=by_owner,
        by_expected_close=_by_expected_close(measured, as_of, base_currency),
        open_pipeline=open_pipeline,
        by_risk_band=_by_risk_band(measured, base_currency, assessed),
        by_customer=by_customer,
        risk_coincidence=_risk_coincidence(by_customer, assessed),
        concentration=_concentrations(by_customer, by_owner, open_pipeline, rate_set),
        per_deal=tuple((one.deal.fact.source_id, one.values) for one in measured),
    )


def valid_deals(
    facts: Iterable[DealFact], stage_vocabulary: Collection[str]
) -> tuple[tuple[ValuedDeal, MoneyValue], ...]:
    """
    Stage 1 of plan A10.5 item 3: every open valued deal with its amount, or an error.

    The reserved-key check, then the stage of each open valued deal, then
    the making of each one's MoneyValue, in that order and each over every
    deal. The frozen type's refusal is neither caught nor translated. The
    deals come back ascending by id.
    """
    valued = sorted((deal for deal in map(valued_deal, facts) if deal is not None),
                    key=_by_source_id)
    stages = sorted(set(stage_vocabulary))
    _check_reserved_keys(valued, stages)
    _check_stages(valued, stages)
    return tuple((deal, MoneyValue(amount=deal.amount, currency=deal.currency))
                 for deal in valued)


def _check_reserved_keys(valued: Sequence[ValuedDeal], stages: Sequence[str]) -> None:
    """
    Plan A10.5 item 1: no generated key may equal a reserved one.

    The generated keys are every value of the stage vocabulary, whose bucket
    is always present, and the currency, the owning employee and, from
    VS02-M3, the customer of each open valued deal. The currency ALL is the
    case plan A10.1 item 3 settles: it is valid Layer 1 data and it fails
    here, whatever the rate set holds.
    """
    collisions = [(deal.fact.source_id, key) for deal in valued for key in _generated_keys(deal)
                  if key in RESERVED_KEYS]
    keys = {stage for stage in stages if stage in RESERVED_KEYS} | {key for _, key in collisions}
    if keys:
        raise PipelineDataError(RESERVED_KEY, keys=keys,
                                source_ids={source_id for source_id, _ in collisions})


def _generated_keys(deal: ValuedDeal) -> tuple[str, ...]:
    """The bucket keys one deal's data generates: its currency and, where it has one, its
    owner and its customer."""
    return (deal.currency,
            *(key for key in (deal.fact.owner, deal.fact.customer) if key is not None))


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


def _by_customer(
    measured: Sequence[_Measured], base_currency: str, assessed: Mapping[str, CustomerBand]
) -> tuple[CustomerBucket, ...]:
    """
    Plan A12.6: one bucket per customer holding a deal, then UNLINKED, always present.

    The customers are ordered by base unweighted exposure, largest first,
    and by id where two are equal. Each carries its stored band and verdict,
    or UNASSESSED and no verdict. A band orders nothing here.
    """
    customers = sorted({customer for one in measured
                        for customer in [one.deal.fact.customer] if customer is not None})
    buckets = [
        _bucket(CustomerBucket, customer,
                [one for one in measured if one.deal.fact.customer == customer], base_currency,
                kind=CustomerKind.CUSTOMER,
                band=UNASSESSED if customer not in assessed else assessed[customer].band.value,
                executive_worthy=(None if customer not in assessed
                                  else assessed[customer].executive_worthy))
        for customer in customers
    ]
    return (
        *sorted(buckets, key=_base_unweighted, reverse=True),
        _bucket(CustomerBucket, UNLINKED,
                [one for one in measured if one.deal.fact.customer is None], base_currency,
                kind=CustomerKind.UNLINKED, band=None, executive_worthy=None),
    )


def _by_risk_band(
    measured: Sequence[_Measured], base_currency: str, assessed: Mapping[str, CustomerBand]
) -> tuple[BandBucket, ...]:
    """
    Plan A12.3: the four bands by descending rank, then UNASSESSED, then UNLINKED.

    All six are always present. The vocabulary and its rank are the frozen
    RiskBand's. A deal sits under its customer's band, under UNASSESSED when
    its customer has no assessment at the identity, and under UNLINKED when
    it has no customer. UNASSESSED is never merged into NONE.
    """
    placed = [(_band_key(one.deal.fact.customer, assessed), one) for one in measured]
    keys = [*(band.value for band in sorted(RiskBand, key=_rank, reverse=True)),
            UNASSESSED, UNLINKED]
    buckets = []
    for key in keys:
        members = [one for placed_key, one in placed if placed_key == key]
        customers = sorted({customer for one in members
                            for customer in [one.deal.fact.customer] if customer is not None})
        buckets.append(_bucket(BandBucket, key, members, base_currency,
                               customer_count=len(customers), customer_ids=tuple(customers)))
    return tuple(buckets)


def _band_key(customer: str | None, assessed: Mapping[str, CustomerBand]) -> str:
    """The one band bucket a deal sits in. The band selects the bucket and does nothing else."""
    if customer is None:
        return UNLINKED
    return UNASSESSED if customer not in assessed else assessed[customer].band.value


def _risk_coincidence(
    by_customer: Sequence[CustomerBucket], assessed: Mapping[str, CustomerBand]
) -> tuple[str, ...]:
    """
    Plan A12.5: the customers at WATCH or above who hold an open valued deal.

    A filter and an order over buckets already built, and no figure. The
    order is lexicographic (A12.4 item 3): band rank descending, then base
    unweighted exposure descending, then id ascending. The buckets arrive in
    the last two orders, and the sort by rank keeps them.
    """
    banded = [(assessed[bucket.key].band, bucket.key) for bucket in by_customer
              if bucket.kind is CustomerKind.CUSTOMER and bucket.key in assessed
              and assessed[bucket.key].band.at_least(RiskBand.WATCH)]
    return tuple(customer for _, customer in sorted(banded, key=_pair_rank, reverse=True))


def _concentrations(
    by_customer: Sequence[CustomerBucket], by_owner: Sequence[OwnerBucket],
    open_pipeline: Bucket, rate_set: RateSet,
) -> Concentrations:
    """
    Plan A11 item 3: by customer and by owner, each unweighted and weighted.

    A pseudo-bucket is a candidate like any other and is flagged, so that
    the shares describe the whole of the open pipeline.
    """
    customers = [(bucket, bucket.kind is not CustomerKind.CUSTOMER) for bucket in by_customer]
    owners = [(bucket, bucket.kind is not OwnerKind.EMPLOYEE) for bucket in by_owner]
    return Concentrations(
        by_customer=ConcentrationPair(
            unweighted=_concentration(
                [(bucket.key, pseudo, bucket.base.unweighted) for bucket, pseudo in customers],
                open_pipeline.base.unweighted, rate_set),
            weighted=_concentration(
                [(bucket.key, pseudo, bucket.base.weighted) for bucket, pseudo in customers],
                open_pipeline.base.weighted, rate_set)),
        by_owner=ConcentrationPair(
            unweighted=_concentration(
                [(bucket.key, pseudo, bucket.base.unweighted) for bucket, pseudo in owners],
                open_pipeline.base.unweighted, rate_set),
            weighted=_concentration(
                [(bucket.key, pseudo, bucket.base.weighted) for bucket, pseudo in owners],
                open_pipeline.base.weighted, rate_set)),
    )


def _concentration(
    candidates: Sequence[tuple[str, bool, Decimal]], whole: Decimal, rate_set: RateSet
) -> Concentration:
    """
    One block over (key, pseudo, amount) candidates and the whole they are parts of.

    A holder is a candidate whose amount is above zero (plan A11 item 4).
    The holders are ordered by amount, largest first, and by key where two
    are equal. A whole of zero has no holder: the block takes its zero form
    and nothing is divided (item 6). The arithmetic is measures.py's.
    """
    if whole.is_zero():
        return Concentration(
            currency=rate_set.base_currency, rate_set_version=rate_set.rate_set_version,
            total=whole, holder_count=0, top=(), cumulative=(), hhi=None,
            reason=NO_OPEN_EXPOSURE)
    holders = sorted(sorted((one for one in candidates if one[2] > 0), key=_candidate_key),
                     key=_candidate_amount, reverse=True)
    amounts = [amount for _, _, amount in holders]
    return Concentration(
        currency=rate_set.base_currency, rate_set_version=rate_set.rate_set_version,
        total=whole, holder_count=len(holders),
        top=tuple(Holder(key=key, pseudo=pseudo, amount=amount, share=share(amount, whole))
                  for key, pseudo, amount in holders[:CONCENTRATION_TOP_N]),
        cumulative=tuple(
            CumulativeShare(holders=point, share=cumulative_share(amounts[:point], whole))
            for point in CUMULATIVE_POINTS),
        hhi=hhi(amounts, whole),
        reason=None)


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


def _base_unweighted(bucket: Bucket) -> Decimal:
    return bucket.base.unweighted


def _rank(band: RiskBand) -> int:
    return band.rank


def _pair_rank(pair: tuple[RiskBand, str]) -> int:
    return pair[0].rank


def _candidate_key(candidate: tuple[str, bool, Decimal]) -> str:
    return candidate[0]


def _candidate_amount(candidate: tuple[str, bool, Decimal]) -> Decimal:
    return candidate[2]
