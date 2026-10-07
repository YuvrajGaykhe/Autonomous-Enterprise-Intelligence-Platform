"""
The pipeline view (VS-02 plan A14): the canonical object, its hash, and what
is rendered from it.

build_view takes one scope, the deal facts and the stored bands read for it,
a rate set, the pipeline rules, the two versions the bands were joined under
and the stage vocabulary, and returns the view as plain JSON values: objects,
lists, strings, integers, booleans and null, and never a float. Every key of
plan A14 is always present. Nothing is added, renamed or omitted.

It is built in this order, and the first condition that fails is the one
raised (plan A17.1, OD-M3-1). Nothing partial is ever returned:

    1. stage 1 of the aggregation      a reserved key, a stage outside the
                                       vocabulary on an open valued deal, or
                                       a refusal by the frozen MoneyValue
    2. deal_counts                     a non-null stage outside the
                                       vocabulary on any deal counted (OD-9)
    3. the stored bands                a band outside the frozen RiskBand
    4. weighting and conversion        a currency with no rate
    5. the partitions, and the view

check_data is the first three by themselves, for the service, which must
examine every currency for a rate after them and before any figure.

deal_counts is the view's own (OD-4). A null stage is UNSTAGED, and nothing
else is: a non-null stage outside the vocabulary leaves no count to state.

A `dec` is VS-01's decimal_text. That function normalises in whatever
Decimal context is in force, so each text is taken inside a context stated
here for that text alone, with as many digits as the number holds: nothing
is rounded in it, and the text is the same whatever context the caller is
in (plan A9.1 items 5 and 6). It is not the arithmetic context, which this
module neither imports nor needs. No figure is computed here.

view_hash is the SHA-256 of VS-01's canonical JSON of the view. The
limitation texts and the citations are rendered from the view, outside the
hash, so a correction to a wording changes no hash (plan A14.10).

This module is pure: no session, no clock, no configuration of its own
loading. The stage vocabulary, the rate set and the rules are handed to it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal, localcontext
from typing import Any

from app.fx.rates import RateSet
from app.intelligence import RecordCitation, Scope
from app.intelligence.contract import canonical_json, decimal_text
from app.pipeline.aggregation import (
    Amount,
    BandBucket,
    Bucket,
    Concentration,
    ConcentrationPair,
    CurrencyBucket,
    CustomerBucket,
    OwnerBucket,
    Partitions,
    PeriodBucket,
    build_partitions,
    valid_deals,
)
from app.pipeline.config import PipelineRules
from app.pipeline.errors import STAGE_OUTSIDE_VOCABULARY, PipelineDataError
from app.pipeline.facts import (
    DEALS,
    BandFact,
    DealFact,
    DealNote,
    DealState,
    customer_bands,
    deal_notes,
    deal_state,
)
from app.pipeline.measures import DealValues

#: Plan A14.2: the version of the view contract itself.
VIEW_VERSION = 1
#: Plan A14.5: the last row of deal_counts.by_stage. It is the row of the
#: deals whose stage is null, and of no other deal (OD-9).
UNSTAGED = "UNSTAGED"
#: Plan A13.2: the one scope-level note. It is emitted when no assessment was
#: read for the identity, and only then (OD-M3-3).
NO_ASSESSMENT_FOR_SCOPE = "NO_ASSESSMENT_FOR_SCOPE"
#: Plan A14.3: a rate set is a stated assumption, and the view says so.
STANDING = "STATED_ASSUMPTION"
#: Plan A13.1 item 2: the stage whose absence the first limitation states.
LOST_STAGE = "lost"
NO_LOST_STAGE = "NO_LOST_STAGE"
#: Plan A13.1: the limitation codes, in the view's order, each with its
#: wording. The wordings are normative, character for character.
LIMITATIONS = (
    (NO_LOST_STAGE,
     "The deal-stage vocabulary is {stages}. It records no lost outcome, so no win rate and no "
     "stage-conversion figure can be stated, and none is."),
    ("NO_ACTUAL_CLOSE_DATE",
     "A closed deal carries an expected close date only. No actual close date exists."),
    ("NO_DEAL_HISTORY",
     "Deals carry no creation or stage-change date. The pipeline is that of the data snapshot; "
     "as_of does not rewind it."),
    ("FX_STATED_ASSUMPTION",
     "Base-currency figures use rate set {rate_set_version}, stated for {rate_as_of_date}. The "
     "rates are an assumption, not a market quotation, and are not matched to as_of."),
    ("SHARES_FOLLOW_RATES",
     "Concentration shares are computed in the base currency and change with the rate set."),
    ("SOURCE_STATED_PROBABILITY",
     "Weighted exposure multiplies each amount by the probability the source system states. It "
     "is not a forecast."),
    ("SINGLE_SOURCE_SYSTEM",
     "Only source system {source_system} is included. Nothing is aggregated across source "
     "systems."),
    ("PERIOD_HORIZON",
     "Expected-close periods are the twelve calendar months from the month of as_of. Later dates "
     "are grouped as LATER."),
    ("BAND_IS_NOT_MONEY",
     "A risk band groups exposure and is never applied to an amount."),
)
#: Plan A18.2 item 2: the fields an open deal's entry may cite beside
#: is_active, each cited when its stated value is not null.
_CITED_WHEN_STATED = ("stage", "amount", "currency", "probability", "expected_close_date",
                      "owner_source_id", "customer_source_id")
#: The resolved customer is grounded by the canonical foreign key.
_CUSTOMER_FIELD = "customer_id"
_STATE_FIELD = "is_active"
_STAGE_FIELD = "stage"


@dataclass(frozen=True)
class PipelineView:
    """What the service returns (plan A22.2): the view, its hash, and what is rendered from it."""

    view: dict[str, Any]
    view_hash: str
    limitation_texts: list[dict[str, str]]
    citations: list[dict[str, object]]


def check_data(
    facts: Iterable[DealFact], bands: Iterable[BandFact], stage_vocabulary: Collection[str]
) -> None:
    """
    The data-validity conditions of plan A17.1's step 5, in OD-M3-1's order.

    Stage 1 exactly as the aggregation runs it, then the stage of every deal
    deal_counts counts, then the band of every stored assessment. Each is
    examined over everything it applies to before the next begins, and the
    first that fails is raised. None of them needs a rate.
    """
    deals = tuple(facts)
    valid_deals(deals, stage_vocabulary)
    deal_counts(deals, stage_vocabulary)
    customer_bands(bands)


def deal_counts(facts: Iterable[DealFact], stage_vocabulary: Collection[str]) -> dict[str, Any]:
    """
    Plan A14.5: every deal in scope, counted by state and by stage.

    by_stage has one row per value of the vocabulary, ascending, and then
    UNSTAGED, each always present. A deal is in exactly one row: its stage's,
    or UNSTAGED when its stage is null. A non-null stage outside the
    vocabulary is neither, so the count is not built and every such deal is
    named (OD-9). A row divides its deals by is_active, as the overall
    counts do.
    """
    deals = sorted(facts, key=_by_source_id)
    stages = sorted(set(stage_vocabulary))
    outside = {fact.source_id for fact in deals
               if fact.stage is not None and fact.stage not in stages}
    if outside:
        raise PipelineDataError(STAGE_OUTSIDE_VOCABULARY, source_ids=outside)
    states = [deal_state(fact) for fact in deals]
    return {
        "total": len(deals),
        "open": len([fact for fact in deals if fact.is_active]),
        "open_valued": states.count(DealState.OPEN_VALUED),
        "open_unvalued": states.count(DealState.OPEN_UNVALUED),
        "closed": len([fact for fact in deals if not fact.is_active]),
        "unvalued_deal_ids": [fact.source_id for fact, state in zip(deals, states, strict=True)
                              if state is DealState.OPEN_UNVALUED],
        "by_stage": [
            *(_stage_row(stage, [fact for fact in deals if fact.stage == stage])
              for stage in stages),
            _stage_row(UNSTAGED, [fact for fact in deals if fact.stage is None]),
        ],
    }


def build_view(
    *,
    scope: Scope,
    facts: Iterable[DealFact],
    bands: Iterable[BandFact],
    rate_set: RateSet,
    rules: PipelineRules,
    rules_version: int,
    linker_version: str,
    stage_vocabulary: Collection[str],
) -> dict[str, Any]:
    """
    The view of plan A14.2 for one scope, or an error and nothing.

    `bands` is every assessment read at the scope's identity under the two
    versions given. When it is empty the scope note is stated, and only
    then, whatever deals the scope holds (plan A13.2 item 4).
    """
    deals = sorted(facts, key=_by_source_id)
    stored = tuple(bands)
    stages = sorted(set(stage_vocabulary))
    check_data(deals, stored, stages)
    counts = deal_counts(deals, stages)
    partitions = build_partitions(deals, rate_set, stages, scope.as_of, stored)
    per_deal = dict(partitions.per_deal)
    return {
        "view_version": VIEW_VERSION,
        "scope": scope.to_payload(),
        "versions": {
            "pipeline_version": rules.pipeline_version,
            "rules_version": rules_version,
            "linker_version": linker_version,
        },
        "fx": _fx(rate_set, partitions),
        "deal_counts": counts,
        "open_pipeline": _bucket(partitions.open_pipeline),
        "by_currency": [_currency_bucket(bucket) for bucket in partitions.by_currency],
        "by_stage": [_bucket(bucket) for bucket in partitions.by_stage],
        "by_owner": [_owner_bucket(bucket) for bucket in partitions.by_owner],
        "by_expected_close": [_period_bucket(bucket) for bucket in partitions.by_expected_close],
        "by_risk_band": [_band_bucket(bucket) for bucket in partitions.by_risk_band],
        "by_customer": [_customer_bucket(bucket) for bucket in partitions.by_customer],
        "risk_coincidence": list(partitions.risk_coincidence),
        "concentration": {
            "by_customer": _concentration_pair(partitions.concentration.by_customer),
            "by_owner": _concentration_pair(partitions.concentration.by_owner),
        },
        "open_deals": [_open_deal(fact, per_deal.get(fact.source_id))
                       for fact in deals if fact.is_active],
        "closed_deals": [_closed_deal(fact) for fact in deals if not fact.is_active],
        "data_quality": _data_quality(deals, stored, rules.closed_stages),
        "limitations": [code for code, _ in LIMITATIONS
                        if code != NO_LOST_STAGE or LOST_STAGE not in stages],
    }


def view_hash(view: dict[str, Any]) -> str:
    """Plan A14.10 item 3: the SHA-256 of the view's canonical JSON, as UTF-8."""
    return hashlib.sha256(canonical_json(view).encode("utf-8")).hexdigest()


def limitation_texts(view: dict[str, Any]) -> list[dict[str, str]]:
    """
    Plan A13.1 item 3: each limitation code of the view with its wording, in the view's order.

    The placeholders are the view's own values. A value is put into a
    wording and is never read as one: a source system that itself holds
    braces is stated as it is.
    """
    stated = {
        "stages": ", ".join(bucket["key"] for bucket in view["by_stage"]),
        "rate_set_version": view["fx"]["rate_set_version"],
        "rate_as_of_date": view["fx"]["rate_as_of_date"],
        "source_system": view["scope"]["source_system"],
    }
    wordings = dict(LIMITATIONS)
    return [{"code": code, "text": wordings[code].format(**stated)}
            for code in view["limitations"]]


def citations(view: dict[str, Any]) -> list[dict[str, object]]:
    """
    Plan A18.2: every deal value the view states, as a record citation, by id and then field.

    Each is built through VS-01's frozen RecordCitation, so only a citable
    field of `deals` can be named. An open deal cites is_active always, each
    stored value its entry states, and its canonical customer key where the
    customer is resolved; a closed deal cites is_active, and its stage where
    it has one.
    """
    cited = []
    for entry in view["open_deals"]:
        fields = [_STATE_FIELD, *(name for name in _CITED_WHEN_STATED if entry[name] is not None)]
        if entry["customer"] is not None:
            fields.append(_CUSTOMER_FIELD)
        cited += [(entry["id"], name) for name in fields]
    for entry in view["closed_deals"]:
        cited.append((entry["id"], _STATE_FIELD))
        if entry[_STAGE_FIELD] is not None:
            cited.append((entry["id"], _STAGE_FIELD))
    return [RecordCitation(DEALS, source_id, name).to_payload()
            for source_id, name in sorted(cited)]


def _fx(rate_set: RateSet, partitions: Partitions) -> dict[str, Any]:
    """Plan A14.3: the whole rate set, and the currencies the open valued deals hold."""
    return {
        "base_currency": rate_set.base_currency,
        "rate_set_version": rate_set.rate_set_version,
        "rate_as_of_date": rate_set.as_of_date.isoformat(),
        "rate_set_digest": rate_set.digest,
        "standing": STANDING,
        "source_note": rate_set.source_note,
        "rates": [{"currency": currency, "rate_to_base": _dec(rate)}
                  for currency, rate in sorted(rate_set.rates.items())],
        "used_currencies": [bucket.key for bucket in partitions.by_currency],
    }


def _stage_row(stage: str, deals: Sequence[DealFact]) -> dict[str, Any]:
    return {
        "stage": stage,
        "total": len(deals),
        "open": len([fact for fact in deals if fact.is_active]),
        "closed": len([fact for fact in deals if not fact.is_active]),
    }


def _amount(amount: Amount) -> dict[str, Any]:
    return {
        "currency": amount.currency,
        "unweighted": _dec(amount.unweighted),
        "weighted": _dec(amount.weighted),
    }


def _bucket(bucket: Bucket) -> dict[str, Any]:
    """Plan A14.4: the five keys every bucket has."""
    return {
        "key": bucket.key,
        "deal_count": bucket.deal_count,
        "deal_ids": list(bucket.deal_ids),
        "native": [_amount(amount) for amount in bucket.native],
        "base": _amount(bucket.base),
    }


def _currency_bucket(bucket: CurrencyBucket) -> dict[str, Any]:
    return {**_bucket(bucket), "rate_to_base": _dec(bucket.rate_to_base)}


def _owner_bucket(bucket: OwnerBucket) -> dict[str, Any]:
    return {
        **_bucket(bucket),
        "kind": bucket.kind.value,
        "basis": None if bucket.basis is None else bucket.basis.value,
        "carrier_field": bucket.carrier_field,
        "unresolved_keys": list(bucket.unresolved_keys),
    }


def _period_bucket(bucket: PeriodBucket) -> dict[str, Any]:
    return {**_bucket(bucket), "kind": bucket.kind.value}


def _band_bucket(bucket: BandBucket) -> dict[str, Any]:
    return {
        **_bucket(bucket),
        "customer_count": bucket.customer_count,
        "customer_ids": list(bucket.customer_ids),
    }


def _customer_bucket(bucket: CustomerBucket) -> dict[str, Any]:
    return {
        **_bucket(bucket),
        "kind": bucket.kind.value,
        "band": bucket.band,
        "executive_worthy": bucket.executive_worthy,
    }


def _concentration_pair(pair: ConcentrationPair) -> dict[str, Any]:
    return {
        "unweighted": _concentration(pair.unweighted),
        "weighted": _concentration(pair.weighted),
    }


def _concentration(block: Concentration) -> dict[str, Any]:
    """Plan A14.7. A block with no exposure states no share and says why."""
    return {
        "currency": block.currency,
        "rate_set_version": block.rate_set_version,
        "total": _dec(block.total),
        "holder_count": block.holder_count,
        "top": [{"key": holder.key, "pseudo": holder.pseudo, "amount": _dec(holder.amount),
                 "share": _dec(holder.share)} for holder in block.top],
        "cumulative": [{"holders": point.holders, "share": _dec(point.share)}
                       for point in block.cumulative],
        "hhi": _optional_dec(block.hhi),
        "reason": block.reason,
    }


def _open_deal(fact: DealFact, values: DealValues | None) -> dict[str, Any]:
    """Plan A14.8: an open deal as stored, with its own values when it is valued."""
    return {
        "id": fact.source_id,
        "state": deal_state(fact).value,
        "stage": fact.stage,
        "is_active": fact.is_active,
        "amount": _optional_dec(fact.amount),
        "currency": fact.currency,
        "probability": _optional_dec(fact.probability),
        "expected_close_date": (None if fact.expected_close_date is None
                                else fact.expected_close_date.isoformat()),
        "owner_source_id": fact.owner_source_id,
        "owner": fact.owner,
        "customer_source_id": fact.customer_source_id,
        "customer": fact.customer,
        "native_weighted": None if values is None else _dec(values.native_weighted.amount),
        "base_unweighted": None if values is None else _dec(values.base_unweighted.amount),
        "base_weighted": None if values is None else _dec(values.base_weighted.amount),
    }


def _closed_deal(fact: DealFact) -> dict[str, Any]:
    """Plan A14.8, MD-5: a closed deal carries its stage and its activity, and no amount."""
    return {"id": fact.source_id, "stage": fact.stage, "is_active": fact.is_active}


def _data_quality(
    deals: Sequence[DealFact], bands: Sequence[BandFact], closed_stages: Collection[str]
) -> list[dict[str, Any]]:
    """
    Plan A13.2: every deal-level note, and the scope note when no assessment was read.

    Ordered by code and then by id, a null id first.
    """
    notes = [_note(note) for fact in deals for note in deal_notes(fact, closed_stages)]
    if not bands:
        notes.append({"code": NO_ASSESSMENT_FOR_SCOPE, "entity": None, "id": None, "fields": [],
                      "key": None})
    return sorted(notes, key=_by_code_and_id)


def _note(note: DealNote) -> dict[str, Any]:
    return {
        "code": note.code.value,
        "entity": note.entity,
        "id": note.id,
        "fields": list(note.fields),
        "key": note.key,
    }


def _dec(value: Decimal) -> str:
    """
    VS-01's decimal_text of a number, whatever Decimal context is in force.

    decimal_text normalises in the current context, so this states one for
    the text alone: as many digits as the number holds, and the widest
    exponents. Normalising is then exact and can raise no signal.
    """
    digits = max(1, len(value.as_tuple().digits))
    with localcontext(Context(prec=digits, Emin=MIN_EMIN, Emax=MAX_EMAX)):
        return decimal_text(value)


def _optional_dec(value: Decimal | None) -> str | None:
    return None if value is None else _dec(value)


def _by_source_id(fact: DealFact) -> str:
    return fact.source_id


def _by_code_and_id(note: dict[str, Any]) -> tuple[str, bool, str]:
    return (note["code"], note["id"] is not None, note["id"] or "")
