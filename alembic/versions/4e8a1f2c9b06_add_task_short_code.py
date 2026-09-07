"""add short_code to tasks — day.task label for the /leaderboard table

Revision ID: 4e8a1f2c9b06
Revises: 9c3f0a7d5b21
Create Date: 2026-09-04 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4e8a1f2c9b06'
down_revision: str | None = '9c3f0a7d5b21'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Необязательный короткий код вида "1.1", "2.3" (день.задание) — если задан,
    # задание попадает колонкой в таблицу /leaderboard (Фаза 21). NULL — задание
    # (например, глобальная миссия) не участвует в таблице по дням, только в общем
    # счёте команды.
    op.add_column('tasks', sa.Column('short_code', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'short_code')
