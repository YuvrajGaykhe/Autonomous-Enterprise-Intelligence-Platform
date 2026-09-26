"""M8: brief_decisions — the append-only decision record on a risk brief

Additive. Chains after the M7 tables and creates exactly one table, its three
indexes, and the trigger function and row trigger that make the table
append-only. No canonical, operational, M4 or M7 table is altered, and
downgrade drops only what this revision created, returning the schema to its
M7 state.

The function and the trigger are the repository's first raw DDL, authorised
for them alone (§0.7.5, OPEN-M8-4). Every other object is created through
op.create_table and op.create_index, as M4's and M7's are; the partial
indexes name their predicates as column expressions, not textual SQL.
TRUNCATE is not blocked: the test harness truncates every table between
tests (§0.7.17).

Revision ID: 070e4968a497
Revises: 66eddc6b7136
Create Date: 2026-09-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '070e4968a497'
down_revision: Union[str, None] = '66eddc6b7136'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# SQLSTATE 23001 reaches SQLAlchemy as IntegrityError.
CREATE_APPEND_ONLY_FUNCTION = """
CREATE FUNCTION brief_decisions_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'brief_decisions is append-only' USING ERRCODE = 'restrict_violation';
END;
$$
"""

CREATE_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER brief_decisions_append_only BEFORE UPDATE OR DELETE ON brief_decisions
    FOR EACH ROW EXECUTE FUNCTION brief_decisions_append_only()
"""


def upgrade() -> None:
    op.create_table(
        'brief_decisions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brief_id', sa.UUID(), nullable=False,
                  comment='The brief the decision was made on'),
        sa.Column('payload_hash', sa.String(length=64), nullable=False,
                  comment="The brief's payload hash the decision is bound to"),
        sa.Column('actor', sa.String(length=255), nullable=False,
                  comment='Who recorded the decision, as supplied; asserted, never verified'),
        sa.Column('decision', sa.String(length=50), nullable=False,
                  comment='APPROVED or REJECTED'),
        sa.Column('note', sa.String(length=2000), nullable=True,
                  comment="The actor's optional note"),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False,
                  comment='When the decision was recorded; always supplied by the caller'),
        sa.Column('supersedes_id', sa.UUID(), nullable=True,
                  comment="The decision this one supersedes; NULL for a brief's first decision"),
        sa.ForeignKeyConstraint(['brief_id'], ['risk_briefs.id'], ondelete='RESTRICT',
                                name=op.f('fk_brief_decisions_brief_id_risk_briefs')),
        sa.ForeignKeyConstraint(['supersedes_id'], ['brief_decisions.id'], ondelete='RESTRICT',
                                name=op.f('fk_brief_decisions_supersedes_id_brief_decisions')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_brief_decisions')),
    )
    op.create_index('ix_brief_decisions_brief_id', 'brief_decisions',
                    ['brief_id'], unique=False)
    op.create_index('uq_brief_decisions_first_decision', 'brief_decisions',
                    ['brief_id'], unique=True,
                    postgresql_where=sa.column('supersedes_id').is_(None))
    op.create_index('uq_brief_decisions_one_successor', 'brief_decisions',
                    ['supersedes_id'], unique=True,
                    postgresql_where=sa.column('supersedes_id').is_not(None))
    op.execute(CREATE_APPEND_ONLY_FUNCTION)
    op.execute(CREATE_APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    op.execute('DROP TRIGGER brief_decisions_append_only ON brief_decisions')
    op.execute('DROP FUNCTION brief_decisions_append_only()')
    op.drop_index('uq_brief_decisions_one_successor', table_name='brief_decisions')
    op.drop_index('uq_brief_decisions_first_decision', table_name='brief_decisions')
    op.drop_index('ix_brief_decisions_brief_id', table_name='brief_decisions')
    op.drop_table('brief_decisions')
