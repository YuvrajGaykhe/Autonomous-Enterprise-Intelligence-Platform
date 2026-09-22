"""
The Sales function's reading of a customer (VS-01 M5, §A16).

One of §A16's six non-`NO_ACTION` entries is Sales's:

    ACCELERATE_DEAL_CLOSE   active deal, stage `negotiation`, probability >= 80

**One position per qualifying deal** (§0.4.1), each contesting that deal, with
stance `ADVANCE` -- the stance that makes the opposition to Support's
`RESTRAIN` legible to a reader of the brief. A customer with two qualifying
deals states two positions; a customer with none states nothing, and emits no
`NO_ACTION` position (§A16 leaves that entry's *Proposed by* column empty).

**No band term.** §A16's precondition carries none, so this function is not
silent for a low-risk customer: of the fifteen ticketless customers in the demo
dataset, the three holding a qualifying deal each state one position and draw
no conflict, because no Support position names their deal (§0.4.8 criterion 8).

**Membership in `active_deals` is M3's answer to "active"**, read here and not
recomputed. This module reads stage and probability, and decides nothing else.

**This module imports neither Session nor any ORM model** (§A14, §0.4.5). It
also holds no ticket record: `CommercialContext` carries the S1-S10 aggregates
as part of the SignalSet but no `TicketFact`, which is the prohibition §A14
places on this side -- on rows, where Support's is on values (§0.4.9 D-M5-B7).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from app.analysts.base import (
    ACCELERATE_PROBABILITY_THRESHOLD,
    DEALS,
    Analyst,
    canonical_fact,
)
from app.analysts.context import CommercialContext
from app.intelligence.contract import ActionId, DealSignal, Function, Position, Stance
from app.intelligence.signals import NEGOTIATION_STAGE


@dataclass(frozen=True)
class CommercialAnalyst(Analyst):
    """
    Sales's position on every qualifying deal, with citations.

    Constructed with a CommercialContext and given nothing else (§A14). The
    result is `tuple[Position, ...]`, one per qualifying deal.
    """

    FUNCTION: ClassVar[Function] = Function.SALES

    context: CommercialContext

    def _proposals(self) -> Iterable[Position]:
        customer = self.context.customer.source_id
        for deal in qualifying_deals(self.context.signals.active_deals):
            yield self._position(
                ActionId.ACCELERATE_DEAL_CLOSE,
                deal.source_id,
                f"{deal.source_id} for {customer} is in {deal.stage} at "
                f"{deal.probability}%, at or above the "
                f"{ACCELERATE_PROBABILITY_THRESHOLD}% threshold for acceleration.",
                [
                    canonical_fact(DEALS, deal.source_id, "is_active"),
                    canonical_fact(DEALS, deal.source_id, "stage"),
                    canonical_fact(DEALS, deal.source_id, "probability"),
                ],
                stance=Stance.ADVANCE,
            )


def qualifying_deals(deals: Iterable[DealSignal]) -> tuple[DealSignal, ...]:
    """
    §A16's ACCELERATE_DEAL_CLOSE precondition, in source-identity order.

    Pure. Ordering by `source_id` here is redundant with the position ordering
    §0.4.1 applies afterwards, and is kept so this predicate is deterministic
    on its own rather than only in the context that calls it.
    """
    return tuple(
        deal for deal in sorted(deals, key=lambda deal: deal.source_id)
        if deal.stage == NEGOTIATION_STAGE
        and deal.probability >= ACCELERATE_PROBABILITY_THRESHOLD
    )
