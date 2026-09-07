"""add personal (per-participant) task dispatch

Revision ID: 7b3c5e9a1d24
Revises: 4e8a1f2c9b06
Create Date: 2026-09-07 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7b3c5e9a1d24'
down_revision: str | None = '4e8a1f2c9b06'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Личные задания (Фаза 22) — рассылаются каждому зарегистрированному участнику
    # отдельно, а не командам (например, «зарегистрируйтесь в бонусном приложении»
    # ещё до распределения по командам).
    op.add_column('tasks', sa.Column('is_personal', sa.Boolean(), nullable=False, server_default='false'))

    # 5-й критерий ("global_mission_submit", 21 символ) не влезал в прежние 20.
    op.alter_column('tasks', 'criterion', existing_type=sa.String(length=20), type_=sa.String(length=32))

    op.alter_column('task_dispatches', 'team_id', existing_type=sa.Integer(), nullable=True)
    op.add_column('task_dispatches', sa.Column('application_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_task_dispatches_application_id_applications',
        'task_dispatches', 'applications', ['application_id'], ['id'],
    )
    op.create_index(
        op.f('ix_task_dispatches_application_id'), 'task_dispatches', ['application_id']
    )
    op.create_unique_constraint(
        'uq_task_dispatches_task_id_application_id', 'task_dispatches', ['task_id', 'application_id']
    )
    op.create_check_constraint(
        'ck_task_dispatch_team_xor_application',
        'task_dispatches',
        'num_nonnulls(team_id, application_id) = 1',
    )


def downgrade() -> None:
    op.alter_column('tasks', 'criterion', existing_type=sa.String(length=32), type_=sa.String(length=20))
    op.drop_constraint('ck_task_dispatch_team_xor_application', 'task_dispatches', type_='check')
    op.drop_constraint('uq_task_dispatches_task_id_application_id', 'task_dispatches', type_='unique')
    op.drop_index(op.f('ix_task_dispatches_application_id'), table_name='task_dispatches')
    op.drop_constraint(
        'fk_task_dispatches_application_id_applications', 'task_dispatches', type_='foreignkey'
    )
    op.drop_column('task_dispatches', 'application_id')
    op.alter_column('task_dispatches', 'team_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('tasks', 'is_personal')
