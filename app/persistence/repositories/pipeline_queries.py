"""
VS-02's reads of Layer 1 (plan A16.2), as far as VS02-M2 has built.

This module is **persistence only**, on the boundary M4 drew (VS-01 plan
§0.3.11 D-M4-B1): it imports no app.intelligence, app.fx or app.pipeline
module, names no domain type, and decides nothing. It returns plain
NamedTuple rows; giving them meaning is the caller's.

It reads and never writes. It holds `select` statements and nothing else
(plan A21.2): every function takes a caller-owned session, nothing here
commits, rolls back, begins, closes or flushes, nothing uses textual SQL,
nothing locks a row, and nothing logs. It creates no engine, connection or
session.

    deal_rows   nine columns of every deal of one source system. It reads no
                other column of `deals`, the deal's name included, and no
                other table.

Every read is ordered inside its statement with the `C` collation on
`source_id`. `C` compares bytes, which for UTF-8 text is code-point order,
so the order never depends on the database's default collation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import Deal

#: The Layer 1 entity the deal read is confined to.
DEALS = "deals"


class DealRow(NamedTuple):
    """The nine `deals` columns VS-02 reads, as stored."""

    source_id: str
    stage: str | None
    is_active: bool
    amount: Decimal | None
    currency: str | None
    probability: Decimal | None
    expected_close_date: date | None
    owner_source_id: str | None
    customer_source_id: str | None


def deal_rows(session: Session, source_system: str) -> list[DealRow]:
    """Every deal of the source system, ascending by `source_id` in code-point order."""
    rows = session.execute(
        select(
            Deal.source_id,
            Deal.stage,
            Deal.is_active,
            Deal.amount,
            Deal.currency,
            Deal.probability,
            Deal.expected_close_date,
            Deal.owner_source_id,
            Deal.customer_source_id,
        )
        .where(Deal.source_system == source_system, Deal.source_entity == DEALS)
        .order_by(Deal.source_id.collate("C"))
    ).all()
    return [DealRow(*row) for row in rows]
