"""drop phone and city from applications — registration is full name only

Revision ID: 9c3f0a7d5b21
Revises: 2f6a9d1c8b47
Create Date: 2026-08-31 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9c3f0a7d5b21'
down_revision: str | None = '2f6a9d1c8b47'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # По решению заказчика (Фаза 17) регистрация — только ФИО: телефон не нужен,
    # задания приходят через сам Telegram-бот; город не нужен для механики
    # экспедиции. Защита от повторной регистрации остаётся на unique(user_id).
    op.drop_index(op.f('ix_applications_phone'), table_name='applications')
    op.drop_column('applications', 'phone')
    op.drop_column('applications', 'city')


def downgrade() -> None:
    op.add_column('applications', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('applications', sa.Column('phone', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_applications_phone'), 'applications', ['phone'], unique=True)
