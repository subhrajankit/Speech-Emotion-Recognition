"""003_transcript_mixed_language_nullable

Makes transcripts.mixed_language nullable so that turns where the pipeline
has not determined mixed-language status persist NULL instead of a
fabricated False. script was already nullable.

Revision ID: c4d8e1f02a91
Revises: b7e2f4a91c03
Create Date: 2026-11-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8e1f02a91'
down_revision: Union[str, Sequence[str], None] = 'b7e2f4a91c03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow NULL mixed_language on transcripts."""
    with op.batch_alter_table('transcripts', schema=None) as batch_op:
        batch_op.alter_column('mixed_language', existing_type=sa.Boolean(), nullable=True)


def downgrade() -> None:
    """Restore NOT NULL constraint.

    WARNING: fails if NULL values were written while nullable.
    """
    with op.batch_alter_table('transcripts', schema=None) as batch_op:
        batch_op.alter_column('mixed_language', existing_type=sa.Boolean(), nullable=False)
