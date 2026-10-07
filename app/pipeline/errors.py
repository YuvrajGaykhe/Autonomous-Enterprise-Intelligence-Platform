"""
Failure model for the pipeline (VS-02 M2, M3).

    PipelineError
        PipelineDataError     the data makes a correct partition impossible
                              (plan A10.5): the calculation stops, and no
                              partition is returned, complete or partial

PipelineConfigError is deliberately NOT a PipelineError, matching the D1, D2,
M1 and FX convention: a rules file that cannot be loaded is a deployment
fault, not a property of the data, and must be distinguishable at the call
site.

A data error identifies what it was raised for and states no amount (plan
A10.5 item 5): the condition, the rows that trigger it and, for a reserved
key, the key. Nothing is dropped, moved, renamed or re-bucketed to avoid it.

The rows are deals for every condition a deal triggers, which is every
condition VS02-M2 raises. From VS02-M3 one condition is not a deal's: a
stored band outside the frozen vocabulary is a customer's assessment (plan
A12.3 item 2). So the error says which entity its ids belong to. `deals` is
the default, and no M2 call site names another (OD-M3-2).
"""

from __future__ import annotations

from collections.abc import Iterable

#: Plan A10.5 items 1 and 2: the two conditions a data check reports.
RESERVED_KEY = "RESERVED_KEY"
STAGE_OUTSIDE_VOCABULARY = "STAGE_OUTSIDE_VOCABULARY"
#: The entity a data error identifies its rows in, unless it names another.
DEALS = "deals"


class PipelineError(Exception):
    """Base exception for the pipeline."""


class PipelineDataError(PipelineError):
    """The data makes a correct partition impossible (plan A10.5)."""

    def __init__(
        self, condition: str, *, source_ids: Iterable[str] = (), keys: Iterable[str] = (),
        entity: str = DEALS,
    ) -> None:
        self.condition = condition
        self.entity = entity
        #: Every row of the entity that triggers the condition, ascending and once each.
        self.source_ids = tuple(sorted(set(source_ids)))
        #: Every reserved key a generated key equals, ascending and once each.
        self.keys = tuple(sorted(set(keys)))
        parts = [condition]
        if self.keys:
            parts.append(f"keys {', '.join(self.keys)}")
        if self.source_ids:
            parts.append(f"{self.entity} {', '.join(self.source_ids)}")
        super().__init__("; ".join(parts))


class PipelineConfigError(Exception):
    """Raised when the pipeline rules configuration is missing or inconsistent."""
