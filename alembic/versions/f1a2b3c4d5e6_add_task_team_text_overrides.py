"""add per-team text overrides to tasks

Revision ID: f1a2b3c4d5e6
Revises: 7b3c5e9a1d24
Create Date: 2026-09-12 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = '7b3c5e9a1d24'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'tasks', sa.Column('team_text_overrides', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('tasks', 'team_text_overrides')
