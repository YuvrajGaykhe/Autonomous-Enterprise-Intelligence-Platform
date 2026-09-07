"""baseline: empty schema, migration pipeline verified

Revision ID: 0001
Revises:
Create Date: 2026-09-07

This is the A3 baseline migration. It performs no schema changes.
Its purpose is to prove that the Alembic migration pipeline
(generate -> upgrade -> downgrade -> upgrade) works correctly
against the Layer 1 PostgreSQL database.

Application tables will be introduced in B1.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline migration. No application tables yet.
    # B1 will add canonical and operational tables.
    pass


def downgrade() -> None:
    # Nothing to reverse.
    pass
