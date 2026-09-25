"""M7: risk_assessments, risk_positions, risk_briefs — the assessment run's results

Additive. Chains after the M4 link table and creates exactly three tables.
No canonical, operational or M4 table is altered, and downgrade drops only
what this revision created, returning the schema to its M4 state.

Revision ID: 66eddc6b7136
Revises: c4a1e97d5b02
Create Date: 2026-09-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '66eddc6b7136'
down_revision: Union[str, None] = 'c4a1e97d5b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'risk_assessments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=True,
                  comment='The assessed customer'),
        sa.Column('as_of', sa.Date(), nullable=False,
                  comment='The evaluation date'),
        sa.Column('source_system', sa.String(length=100), nullable=False,
                  comment='The one source system the assessment was computed over'),
        sa.Column('layer1_fingerprint', sa.String(length=64), nullable=False,
                  comment='The Layer 1 snapshot the assessment was computed from'),
        sa.Column('rules_version', sa.Integer(), nullable=False,
                  comment='The risk-rule configuration version'),
        sa.Column('linker_version', sa.String(length=50), nullable=False,
                  comment='The document-linker version'),
        sa.Column('band', sa.String(length=50), nullable=False,
                  comment='The assigned risk band'),
        sa.Column('executive_worthy', sa.Boolean(), nullable=False,
                  comment="The reconciliation's executive-worthiness verdict, verbatim"),
        sa.Column('signals', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='The signal values the band was assigned from'),
        sa.Column('satisfied_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='The satisfied band-rule ids, in band-table order'),
        sa.Column('ranking_key', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment="The reconciliation's ranking key, verbatim"),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL',
                                name=op.f('fk_risk_assessments_customer_id_customers')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_assessments')),
        sa.UniqueConstraint('customer_id', 'as_of', 'source_system', 'layer1_fingerprint',
                            'rules_version', 'linker_version',
                            name='uq_risk_assessments_identity'),
    )
    op.create_index('ix_risk_assessments_customer_id', 'risk_assessments',
                    ['customer_id'], unique=False)

    op.create_table(
        'risk_positions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('assessment_id', sa.UUID(), nullable=False,
                  comment='The assessment that owns this position'),
        sa.Column('ordinal', sa.Integer(), nullable=False,
                  comment="The position's index in the ordered positions, from 0"),
        sa.Column('function', sa.String(length=50), nullable=False,
                  comment='The function that stated the position'),
        sa.Column('stance', sa.String(length=50), nullable=False,
                  comment="The function's stance toward the contested object"),
        sa.Column('proposed_action', sa.String(length=50), nullable=False,
                  comment='The proposed action-catalogue id'),
        sa.Column('object_ref', sa.String(length=255), nullable=False,
                  comment='The source id of the object the action applies to'),
        sa.Column('rationale', sa.Text(), nullable=False,
                  comment="The position's stated rationale"),
        sa.Column('citations', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment="The position's evidence: each item's kind, citation and any rule id"),
        sa.ForeignKeyConstraint(['assessment_id'], ['risk_assessments.id'], ondelete='CASCADE',
                                name=op.f('fk_risk_positions_assessment_id_risk_assessments')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_positions')),
        sa.UniqueConstraint('assessment_id', 'function', 'object_ref', 'proposed_action',
                            name='uq_risk_positions_identity'),
    )
    op.create_index('ix_risk_positions_assessment_id', 'risk_positions',
                    ['assessment_id'], unique=False)

    op.create_table(
        'risk_briefs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('assessment_id', sa.UUID(), nullable=False,
                  comment='The assessment the brief was generated for'),
        sa.Column('policy_version', sa.Integer(), nullable=False,
                  comment='The conflict-policy version the brief was reconciled under'),
        sa.Column('template_version', sa.String(length=50), nullable=False,
                  comment='The narrative template version; stored, never hashed'),
        sa.Column('decision_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment='The hashed decision payload'),
        sa.Column('payload_hash', sa.String(length=64), nullable=False,
                  comment='SHA-256 of the canonical decision payload'),
        sa.Column('narrative', sa.Text(), nullable=False,
                  comment='The narrative rendered from the payload; a view, not hashed'),
        sa.Column('status', sa.String(length=50), server_default='DRAFT', nullable=False,
                  comment="The brief's approval status"),
        sa.ForeignKeyConstraint(['assessment_id'], ['risk_assessments.id'], ondelete='CASCADE',
                                name=op.f('fk_risk_briefs_assessment_id_risk_assessments')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_briefs')),
        sa.UniqueConstraint('assessment_id', 'payload_hash', name='uq_risk_briefs_identity'),
    )
    op.create_index('ix_risk_briefs_assessment_id', 'risk_briefs',
                    ['assessment_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_risk_briefs_assessment_id', table_name='risk_briefs')
    op.drop_table('risk_briefs')
    op.drop_index('ix_risk_positions_assessment_id', table_name='risk_positions')
    op.drop_table('risk_positions')
    op.drop_index('ix_risk_assessments_customer_id', table_name='risk_assessments')
    op.drop_table('risk_assessments')
