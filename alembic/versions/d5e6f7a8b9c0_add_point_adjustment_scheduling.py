"""add point adjustment scheduling

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-16 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd5e6f7a8b9c0'
down_revision: str | None = 'c4d5e6f7a8b9'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'team_point_adjustments', sa.Column('send_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'team_point_adjustments', sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'team_point_adjustments',
        sa.Column('notify_scope', sa.String(20), nullable=False, server_default='team'),
    )
    op.add_column(
        'team_point_adjustments',
        sa.Column(
            'participant_id', sa.Integer(), sa.ForeignKey('applications.id'), nullable=True
        ),
    )
    # Существующие корректировки уже были применены сразу в момент создания.
    op.execute(
        "UPDATE team_point_adjustments SET send_at = created_at, applied_at = created_at "
        "WHERE send_at IS NULL"
    )
    op.alter_column('team_point_adjustments', 'send_at', nullable=False)


def downgrade() -> None:
    op.drop_column('team_point_adjustments', 'participant_id')
    op.drop_column('team_point_adjustments', 'notify_scope')
    op.drop_column('team_point_adjustments', 'applied_at')
    op.drop_column('team_point_adjustments', 'send_at')
