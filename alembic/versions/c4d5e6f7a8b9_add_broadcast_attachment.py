"""add broadcast attachment fields

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-16 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4d5e6f7a8b9'
down_revision: str | None = 'b3c4d5e6f7a8'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('broadcasts', sa.Column('attachment_photo_key', sa.String(255), nullable=True))
    op.add_column('broadcasts', sa.Column('attachment_video_key', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('broadcasts', 'attachment_video_key')
    op.drop_column('broadcasts', 'attachment_photo_key')
