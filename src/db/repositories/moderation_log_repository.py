from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.moderation_log import ModerationLog
from src.shared.enums import ModerationAction


async def create_log(
    session: AsyncSession,
    *,
    application_id: int,
    admin_user_id: int,
    action: ModerationAction,
    reason: str | None = None,
) -> ModerationLog:
    log = ModerationLog(
        application_id=application_id,
        admin_user_id=admin_user_id,
        action=action,
        reason=reason,
    )
    session.add(log)
    await session.flush()
    return log


async def list_logs_for_application(
    session: AsyncSession, application_id: int
) -> list[ModerationLog]:
    result = await session.execute(
        select(ModerationLog)
        .where(ModerationLog.application_id == application_id)
        .options(selectinload(ModerationLog.admin_user))
        .order_by(ModerationLog.created_at.desc())
    )
    return list(result.scalars().all())
