"""governed definitions, trust badges and the verified-answer library

Revision ID: 9c1e4b7a2d3f
Revises: 36deebb32fb5
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import Text

# revision identifiers, used by Alembic.
revision: str = '9c1e4b7a2d3f'
down_revision: Union[str, Sequence[str], None] = '36deebb32fb5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    """Upgrade schema."""
    # Metrics, default filters and rules live inside the semantic layer's existing JSON column
    # (older versions simply have none), so only chat and the verified library need new storage.
    with op.batch_alter_table('messages') as batch:
        batch.add_column(sa.Column('trust', sa.String(length=16), nullable=True))
        batch.add_column(sa.Column('grounding', JSON, nullable=True))
    with op.batch_alter_table('query_logs') as batch:
        batch.add_column(sa.Column('trust', sa.String(length=16), nullable=True))

    op.create_table('verified_queries',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('dataset_id', sa.String(length=36), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('question_norm', sa.String(length=500), nullable=False),
    sa.Column('sql', sa.Text(), nullable=False),
    sa.Column('sql_norm', sa.Text(), nullable=False),
    sa.Column('standalone', sa.Boolean(), nullable=False),
    sa.Column('source_message_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_message_id'], ['messages.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dataset_id', 'question_norm')
    )
    op.create_index(op.f('ix_verified_queries_dataset_id'), 'verified_queries', ['dataset_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_verified_queries_dataset_id'), table_name='verified_queries')
    op.drop_table('verified_queries')
    with op.batch_alter_table('query_logs') as batch:
        batch.drop_column('trust')
    with op.batch_alter_table('messages') as batch:
        batch.drop_column('grounding')
        batch.drop_column('trust')
