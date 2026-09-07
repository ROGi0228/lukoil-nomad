"""pivot: drop selection/OCR fields, add task scoring criteria

Revision ID: 2f6a9d1c8b47
Revises: 7e2f9b1c4a3d
Create Date: 2026-08-31 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '2f6a9d1c8b47'
down_revision: str | None = '7e2f9b1c4a3d'
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Пивот концепции (Фаза 14) — реальных заявок в проде ещё не было, старые
    # поля отбора/OCR удаляются без сохранения данных.
    op.drop_index(op.f('ix_applications_document_iin'), table_name='applications')
    op.drop_column('applications', 'document_photo_key')
    op.drop_column('applications', 'document_number')
    op.drop_column('applications', 'document_iin')
    op.drop_column('applications', 'document_expiry_date')
    op.drop_column('applications', 'ocr_raw_data')
    op.drop_column('applications', 'verification_flags')
    op.drop_column('applications', 'video_key')
    op.drop_column('applications', 'participant_number')
    op.drop_column('applications', 'selection_stage')
    op.drop_column('applications', 'is_blogger')
    op.drop_column('applications', 'status')

    op.drop_index(op.f('ix_moderation_logs_application_id'), table_name='moderation_logs')
    op.drop_table('moderation_logs')

    # Фаза 15 — гибкая система оценки заданий (3 критерия)
    op.add_column(
        'tasks',
        sa.Column(
            'criterion',
            sa.Enum('pass_fail', 'speed_rank', 'manual', name='taskcriterion', native_enum=False, length=20),
            server_default='pass_fail',
            nullable=False,
        ),
    )
    op.add_column(
        'tasks', sa.Column('pass_points', sa.Integer(), server_default='5', nullable=False)
    )
    op.add_column(
        'tasks',
        sa.Column(
            'rank_points',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[30, 20, 10]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column('tasks', 'penalty_points', server_default='0')


def downgrade() -> None:
    op.alter_column('tasks', 'penalty_points', server_default='2')
    op.drop_column('tasks', 'rank_points')
    op.drop_column('tasks', 'pass_points')
    op.drop_column('tasks', 'criterion')

    op.create_table(
        'moderation_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('admin_user_id', sa.Integer(), nullable=False),
        sa.Column(
            'action',
            sa.Enum(
                'approve',
                'reject',
                'request_reupload_photo',
                'request_reupload_video',
                'approve_document',
                'admin_message',
                name='moderationaction',
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['admin_user_id'], ['admin_users.id']),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_moderation_logs_application_id'), 'moderation_logs', ['application_id'], unique=False
    )

    op.add_column(
        'applications',
        sa.Column(
            'status',
            sa.Enum(
                'draft',
                'pending_document',
                'pending_ocr',
                'document_flagged',
                'pending_video',
                'pending_moderation',
                'approved',
                'rejected',
                name='applicationstatus',
                native_enum=False,
                length=30,
            ),
            server_default='draft',
            nullable=False,
        ),
    )
    op.add_column('applications', sa.Column('is_blogger', sa.Boolean(), server_default='false', nullable=False))
    op.add_column(
        'applications',
        sa.Column(
            'selection_stage',
            sa.Enum(
                'voting', 'eliminated_stage1', 'winner', 'eliminated_stage2',
                name='selectionstage', native_enum=False, length=30,
            ),
            nullable=True,
        ),
    )
    op.add_column('applications', sa.Column('participant_number', sa.String(length=20), nullable=True))
    op.add_column('applications', sa.Column('video_key', sa.String(length=255), nullable=True))
    op.add_column('applications', sa.Column('verification_flags', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('applications', sa.Column('ocr_raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('applications', sa.Column('document_expiry_date', sa.Date(), nullable=True))
    op.add_column('applications', sa.Column('document_iin', sa.String(length=12), nullable=True))
    op.add_column('applications', sa.Column('document_number', sa.String(length=50), nullable=True))
    op.add_column('applications', sa.Column('document_photo_key', sa.String(length=255), nullable=True))
    op.create_unique_constraint(None, 'applications', ['participant_number'])
    op.create_unique_constraint(None, 'applications', ['document_number'])
    op.create_index(op.f('ix_applications_document_iin'), 'applications', ['document_iin'], unique=True)
