from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.user import User


async def list_all_user_contacts(session: AsyncSession) -> list[tuple[int, str | None]]:
    """(telegram_id, language) буквально всех, кто хоть раз нажал /start — для массовой рассылки."""
    result = await session.execute(select(User.telegram_id, User.language))
    return list(result.tuples())


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, telegram_username: str | None
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is not None:
        if user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
        return user

    user = User(telegram_id=telegram_id, telegram_username=telegram_username)
    session.add(user)
    await session.flush()
    return user
