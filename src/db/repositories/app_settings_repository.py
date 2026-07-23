from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.app_settings import AppSettings

_SETTINGS_ROW_ID = 1


async def _get_or_create_settings(session: AsyncSession) -> AppSettings:
    settings = await session.get(AppSettings, _SETTINGS_ROW_ID)
    if settings is None:
        settings = AppSettings(id=_SETTINGS_ROW_ID, registration_closed=False)
        session.add(settings)
        await session.flush()
    return settings


async def is_registration_closed(session: AsyncSession) -> bool:
    settings = await _get_or_create_settings(session)
    return settings.registration_closed


async def set_registration_closed(session: AsyncSession, closed: bool) -> None:
    settings = await _get_or_create_settings(session)
    settings.registration_closed = closed
