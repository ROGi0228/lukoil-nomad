import datetime as dt

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.application import Application
from src.db.models.user import User


async def get_application_by_user_id(session: AsyncSession, user_id: int) -> Application | None:
    result = await session.execute(
        select(Application)
        .where(Application.user_id == user_id)
        .options(selectinload(Application.team))
    )
    return result.scalar_one_or_none()


async def get_application(session: AsyncSession, application_id: int) -> Application | None:
    return await session.get(
        Application, application_id, options=[selectinload(Application.team)]
    )


async def create_application(session: AsyncSession, *, user_id: int, full_name: str) -> Application:
    application = Application(
        user_id=user_id,
        full_name=full_name,
        pdn_consent_at=dt.datetime.now(dt.UTC),
    )
    session.add(application)
    await session.flush()
    return application


async def list_all_applications(session: AsyncSession) -> list[Application]:
    """Все зарегистрированные участники (без пагинации) — для выпадающего списка
    получателя в рассылке из админки."""
    result = await session.execute(select(Application).order_by(Application.full_name))
    return list(result.scalars().all())


async def list_unassigned_applications(session: AsyncSession) -> list[Application]:
    """Зарегистрированные участники, ещё не состоящие ни в одной команде —
    пул для добавления в команду в админке (Фаза 14, заменяет прежние
    «победителей»/«блогеров» из отменённого отбора)."""
    result = await session.execute(
        select(Application).where(Application.team_id.is_(None)).order_by(Application.full_name)
    )
    return list(result.scalars().all())


async def list_all_applications_contacts(session: AsyncSession) -> list[tuple[int, str | None]]:
    """(telegram_id, language) всех зарегистрированных участников — аудитория
    «все зарегистрированные» массовой рассылки из админки."""
    result = await session.execute(
        select(User.telegram_id, User.language).join(Application, Application.user_id == User.id)
    )
    return list(result.tuples())


async def get_application_contact(
    session: AsyncSession, application_id: int
) -> tuple[int, str | None] | None:
    """(telegram_id, language) одной заявки — для личного сообщения из рассылки."""
    result = await session.execute(
        select(User.telegram_id, User.language)
        .join(Application, Application.user_id == User.id)
        .where(Application.id == application_id)
    )
    return result.tuples().first()


async def count_applications(session: AsyncSession) -> int:
    return (await session.execute(select(func.count(Application.id)))).scalar_one()


async def list_applications(
    session: AsyncSession,
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Application], int]:
    conditions: list[ColumnElement[bool]] = []
    if date_from is not None:
        conditions.append(Application.created_at >= date_from)
    if date_to is not None:
        conditions.append(Application.created_at < date_to + dt.timedelta(days=1))
    if search:
        conditions.append(Application.full_name.ilike(f"%{search}%"))

    base_query = select(Application).options(selectinload(Application.team))
    if conditions:
        base_query = base_query.where(and_(*conditions))

    total = (
        await session.execute(select(func.count()).select_from(base_query.subquery()))
    ).scalar_one()

    page_query = (
        base_query.order_by(Application.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    applications = list((await session.execute(page_query)).scalars().all())
    return applications, total
