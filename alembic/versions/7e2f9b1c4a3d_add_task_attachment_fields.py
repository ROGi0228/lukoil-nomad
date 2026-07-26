"""add task attachment fields

Revision ID: 7e2f9b1c4a3d
Revises: 43d07c9f77c9
Create Date: 2026-07-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7e2f9b1c4a3d'
down_revision: str | None = '43d07c9f77c9'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('attachment_photo_key', sa.String(length=255), nullable=True))
    op.add_column('tasks', sa.Column('attachment_video_key', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'attachment_video_key')
    op.drop_column('tasks', 'attachment_photo_key')
