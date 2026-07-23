import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.application import Application
from src.db.models.user import User
from src.shared.enums import ApplicationStatus, SelectionStage

_ALMATY_TZ = ZoneInfo("Asia/Almaty")

# Заявки, ещё не дошедшие до модерации — им отправляется уведомление при закрытии
# приёма заявок. PENDING_MODERATION/APPROVED/REJECTED не трогаем: там участник уже
# полностью прошёл свою часть, решение по нему не зависит от приёма новых заявок.
_INCOMPLETE_STATUSES = (
    ApplicationStatus.DRAFT,
    ApplicationStatus.PENDING_DOCUMENT,
    ApplicationStatus.PENDING_OCR,
    ApplicationStatus.DOCUMENT_FLAGGED,
    ApplicationStatus.PENDING_VIDEO,
)


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


async def list_incomplete_applicants(session: AsyncSession) -> list[tuple[int, str | None]]:
    """(telegram_id, language) всех, чья заявка не дошла до модерации — для рассылки
    уведомления при закрытии приёма заявок."""
    result = await session.execute(
        select(User.telegram_id, User.language)
        .join(Application, Application.user_id == User.id)
        .where(Application.status.in_(_INCOMPLETE_STATUSES))
    )
    return list(result.tuples())


async def list_stage1_candidates(session: AsyncSession) -> list[Application]:
    """Одобренные заявки, ещё не участвующие ни в каком отборе — кандидаты на этап 1."""
    result = await session.execute(
        select(Application)
        .where(Application.status == ApplicationStatus.APPROVED)
        .where(Application.selection_stage.is_(None))
        .order_by(Application.participant_number)
    )
    return list(result.scalars().all())


async def list_stage2_candidates(session: AsyncSession) -> list[Application]:
    """Прошедшие в голосование (этап 1) — кандидаты на финальную победу."""
    result = await session.execute(
        select(Application)
        .where(Application.selection_stage == SelectionStage.VOTING)
        .order_by(Application.participant_number)
    )
    return list(result.scalars().all())


async def list_winners_and_bloggers_contacts(session: AsyncSession) -> list[tuple[int, str | None]]:
    """(telegram_id, language) победителей и отмеченных блогеров — основная аудитория
    массовой рассылки из админки (Фаза 13)."""
    result = await session.execute(
        select(User.telegram_id, User.language)
        .join(Application, Application.user_id == User.id)
        .where(
            or_(
                Application.selection_stage == SelectionStage.WINNER,
                Application.is_blogger.is_(True),
            )
        )
    )
    return list(result.tuples())


async def next_participant_number(session: AsyncSession) -> str:
    """Возвращает следующий номер участника в формате NOMAD_001.

    Простой подсчёт уже присвоенных номеров, без отдельной SQL-последовательности —
    при реальном масштабе (~100 участников, одобрение по одному через админ-панель)
    гонки по этому счётчику практически исключены.
    """
    count = (
        await session.execute(
            select(func.count()).where(Application.participant_number.is_not(None))
        )
    ).scalar_one()
    return f"NOMAD_{count + 1:03d}"


async def has_announced_in_channel_today(
    session: AsyncSession, *, exclude_application_id: int
) -> bool:
    """Был ли сегодня (по времени Алматы) уже хотя бы один пост в канал с видео
    одобренного участника — чтобы не здороваться в подписи повторно за один день."""
    now_almaty = dt.datetime.now(_ALMATY_TZ)
    day_start = now_almaty.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + dt.timedelta(days=1)

    count = (
        await session.execute(
            select(func.count()).where(
                Application.id != exclude_application_id,
                Application.participant_number.is_not(None),
                Application.video_key.is_not(None),
                Application.updated_at >= day_start,
                Application.updated_at < day_end,
            )
        )
    ).scalar_one()
    return count > 0


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
