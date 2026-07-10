import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.application import Application
from src.shared.enums import ApplicationStatus


async def get_application_by_user_id(session: AsyncSession, user_id: int) -> Application | None:
    result = await session.execute(select(Application).where(Application.user_id == user_id))
    return result.scalar_one_or_none()


async def create_application(
    session: AsyncSession,
    *,
    user_id: int,
    full_name: str,
    phone: str,
    city: str,
) -> Application:
    application = Application(
        user_id=user_id,
        full_name=full_name,
        phone=phone,
        city=city,
        status=ApplicationStatus.PENDING_DOCUMENT,
        pdn_consent_at=dt.datetime.now(dt.UTC),
    )
    session.add(application)
    await session.flush()
    return application
