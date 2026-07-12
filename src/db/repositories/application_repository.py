import datetime as dt

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.application import Application
from src.shared.enums import ApplicationStatus


async def get_application_by_user_id(session: AsyncSession, user_id: int) -> Application | None:
    result = await session.execute(select(Application).where(Application.user_id == user_id))
    return result.scalar_one_or_none()


async def get_application(session: AsyncSession, application_id: int) -> Application | None:
    return await session.get(Application, application_id)


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


async def count_applications_by_status(session: AsyncSession) -> dict[ApplicationStatus, int]:
    result = await session.execute(
        select(Application.status, func.count(Application.id)).group_by(Application.status)
    )
    counts: dict[ApplicationStatus, int] = dict.fromkeys(ApplicationStatus, 0)
    for status, count in result.all():
        counts[status] = count
    return counts


async def list_applications(
    session: AsyncSession,
    *,
    status: ApplicationStatus | None = None,
    city: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Application], int]:
    conditions = []
    if status is not None:
        conditions.append(Application.status == status)
    if city:
        conditions.append(Application.city.ilike(f"%{city}%"))
    if date_from is not None:
        conditions.append(Application.created_at >= date_from)
    if date_to is not None:
        conditions.append(Application.created_at < date_to + dt.timedelta(days=1))
    if search:
        like = f"%{search}%"
        conditions.append(or_(Application.full_name.ilike(like), Application.phone.ilike(like)))

    base_query = select(Application)
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
