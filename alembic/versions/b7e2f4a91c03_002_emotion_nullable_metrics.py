"""002_emotion_nullable_metrics

Makes emotion_results.confidence, valence, and arousal nullable so that
turns without genuine model scores persist NULL instead of fabricated
constants or lookup-table approximations.
primary_emotion remains NOT NULL: an EmotionResult row is only created
when a real emotion label exists.

Revision ID: b7e2f4a91c03
Revises: 4acca05d22ce
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2f4a91c03'
down_revision: Union[str, Sequence[str], None] = '4acca05d22ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow NULL confidence/valence/arousal on emotion_results."""
    with op.batch_alter_table('emotion_results', schema=None) as batch_op:
        batch_op.alter_column('confidence', existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('valence', existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('arousal', existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    """Restore NOT NULL constraints.

    WARNING: fails if NULL values were written while nullable.
    """
    with op.batch_alter_table('emotion_results', schema=None) as batch_op:
        batch_op.alter_column('confidence', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('valence', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('arousal', existing_type=sa.Float(), nullable=False)
