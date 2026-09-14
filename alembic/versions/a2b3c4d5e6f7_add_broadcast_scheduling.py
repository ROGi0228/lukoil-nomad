"""add broadcast scheduling

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-14 08:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a2b3c4d5e6f7'
down_revision: str | None = 'f1a2b3c4d5e6'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'broadcasts', sa.Column('audience', sa.String(20), nullable=False, server_default='all')
    )
    op.add_column(
        'broadcasts', sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=True)
    )
    op.add_column(
        'broadcasts',
        sa.Column('participant_id', sa.Integer(), sa.ForeignKey('applications.id'), nullable=True),
    )
    op.add_column(
        'broadcasts', sa.Column('send_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'broadcasts', sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True)
    )
    # Существующие рассылки уходили сразу — считаем их отправленными в момент
    # создания, иначе крон отложенных рассылок попытался бы разослать их заново.
    op.execute("UPDATE broadcasts SET send_at = created_at, sent_at = created_at WHERE send_at IS NULL")
    op.alter_column('broadcasts', 'send_at', nullable=False)


def downgrade() -> None:
    op.drop_column('broadcasts', 'sent_at')
    op.drop_column('broadcasts', 'send_at')
    op.drop_column('broadcasts', 'participant_id')
    op.drop_column('broadcasts', 'team_id')
    op.drop_column('broadcasts', 'audience')
