"""M4: document_customer_links — derived Document to Customer evidence

Additive. Chains after the B1 Layer 1 schema and creates exactly one table.
No canonical or operational table is altered, no column is added to
`documents` or `customers`, and downgrade drops only what this revision
created, returning the schema to its B1 state.

Revision ID: c4a1e97d5b02
Revises: 8bfd73b6af60
Create Date: 2026-09-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4a1e97d5b02'
down_revision: Union[str, None] = '8bfd73b6af60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'document_customer_links',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False,
                  comment="The document whose text asserts the relationship"),
        sa.Column('customer_id', sa.UUID(), nullable=False,
                  comment="The customer the document's text names"),
        sa.Column('basis', sa.String(length=50), nullable=False,
                  comment='LinkBasis: how the match was made (ID_TOKEN or EXACT_NAME)'),
        sa.Column('matched_token', sa.String(length=255), nullable=False,
                  comment="The matched text exactly as the document writes it"),
        sa.Column('match_start', sa.Integer(), nullable=False,
                  comment="Half-open span start in the document's citable text"),
        sa.Column('match_end', sa.Integer(), nullable=False,
                  comment="Half-open span end in the document's citable text"),
        sa.Column('linker_version', sa.String(length=50), nullable=False,
                  comment='The matching rules that derived this link'),
        sa.Column('layer1_fingerprint', sa.String(length=64), nullable=False,
                  comment='The Layer 1 snapshot this link was derived from'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE',
                                name=op.f('fk_document_customer_links_customer_id_customers')),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE',
                                name=op.f('fk_document_customer_links_document_id_documents')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_document_customer_links')),
        sa.UniqueConstraint('document_id', 'customer_id', 'basis', 'linker_version',
                            'layer1_fingerprint',
                            name='uq_document_customer_links_identity'),
    )
    op.create_index('ix_document_customer_links_customer_id', 'document_customer_links',
                    ['customer_id'], unique=False)
    op.create_index('ix_document_customer_links_document_id', 'document_customer_links',
                    ['document_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_document_customer_links_document_id',
                  table_name='document_customer_links')
    op.drop_index('ix_document_customer_links_customer_id',
                  table_name='document_customer_links')
    op.drop_table('document_customer_links')
