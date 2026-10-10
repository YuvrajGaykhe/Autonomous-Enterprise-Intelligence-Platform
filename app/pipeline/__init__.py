"""
Revenue and pipeline intelligence (VS-02), as far as VS02-M2 has built.

The open pipeline, read from frozen Layer 1 rows and divided four ways, with
every cross-currency figure stated through one rate set and never otherwise.
This package reads. It adds no table, no migration and no persistence, and
it changes nothing Layer 1 or VS-01 computes.

Public API:
    PipelineRules / load_pipeline_rules / default_pipeline_rules
                      the authored rules and the methodology digest that
                      identifies everything able to change a figure. Loaded
                      on first use, never at import or startup.
    DealFact / read_deal_facts
                      what VS-02 reads of each deal, with its owner and its
                      customer resolved through the relationship model.
    DealState / OwnerKind / DealNote / NoteCode
    deal_state / owner_kind / deal_notes
                      how each deal is classified, and the data-quality
                      notes it draws. A deal that cannot be valued is counted
                      and reported, never dropped.
    build_partitions / Partitions
    Amount / Bucket / CurrencyBucket / OwnerBucket / PeriodBucket / PeriodKind
                      the four partitions of the open valued deals: by
                      currency, by stage, by owner and by expected-close
                      period. Each sums exactly to the open pipeline.
    PipelineError / PipelineDataError / PipelineConfigError
                      data that makes a correct partition impossible fails
                      closed: no partition is returned, complete or partial.

Determinism is structural: nothing here reads a clock or an environment
variable, every list is ordered where it is built, and all arithmetic runs
in the explicit Decimal context of app.fx. A boundary test fails the build if
any of that changes.
"""

from app.pipeline.aggregation import (
    Amount,
    Bucket,
    CurrencyBucket,
    OwnerBucket,
    Partitions,
    PeriodBucket,
    PeriodKind,
    build_partitions,
)
from app.pipeline.config import PipelineRules, default_pipeline_rules, load_pipeline_rules
from app.pipeline.errors import PipelineConfigError, PipelineDataError, PipelineError
from app.pipeline.facts import (
    DealFact,
    DealNote,
    DealState,
    NoteCode,
    OwnerKind,
    deal_notes,
    deal_state,
    owner_kind,
    read_deal_facts,
)

__all__ = [
    "Amount",
    "Bucket",
    "CurrencyBucket",
    "DealFact",
    "DealNote",
    "DealState",
    "NoteCode",
    "OwnerBucket",
    "OwnerKind",
    "Partitions",
    "PeriodBucket",
    "PeriodKind",
    "PipelineConfigError",
    "PipelineDataError",
    "PipelineError",
    "PipelineRules",
    "build_partitions",
    "deal_notes",
    "deal_state",
    "default_pipeline_rules",
    "load_pipeline_rules",
    "owner_kind",
    "read_deal_facts",
]
