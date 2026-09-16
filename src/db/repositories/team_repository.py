import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.application import Application
from src.db.models.task_dispatch import TaskDispatch
from src.db.models.team import Team
from src.db.models.team_point_adjustment import TeamPointAdjustment
from src.db.models.user import User


async def create_team(session: AsyncSession, name: str) -> Team:
    team = Team(name=name)
    session.add(team)
    await session.flush()
    return team


async def get_team(session: AsyncSession, team_id: int) -> Team | None:
    result = await session.execute(
        select(Team).where(Team.id == team_id).options(selectinload(Team.members))
    )
    return result.scalar_one_or_none()


async def list_teams(session: AsyncSession) -> list[Team]:
    result = await session.execute(
        select(Team).options(selectinload(Team.members)).order_by(Team.name)
    )
    return list(result.scalars().all())


async def list_team_member_contacts(session: AsyncSession, team_id: int) -> list[tuple[int, str | None]]:
    """(telegram_id, language) всех участников команды — для рассылки заданий/результатов."""
    result = await session.execute(
        select(User.telegram_id, User.language)
        .join(Application, Application.user_id == User.id)
        .where(Application.team_id == team_id)
    )
    return list(result.tuples())


async def list_all_team_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(Team.id))
    return list(result.scalars().all())


async def get_team_score(session: AsyncSession, team_id: int) -> int:
    """Командные диспетчи + ручные корректировки + личные диспетчи ТЕКУЩИХ участников
    команды (Task.is_personal — сданы ещё до распределения по командам, но должны
    засчитываться в счёт той команды, куда участник в итоге попал). Считается по
    актуальному Application.team_id на момент вызова, а не "замороженной" на
    момент сдачи команде — если участника позже переведут в другую команду, его
    личные баллы поедут вместе с ним."""
    dispatch_result = await session.execute(
        select(func.coalesce(func.sum(TaskDispatch.points_awarded), 0)).where(
            TaskDispatch.team_id == team_id
        )
    )
    personal_result = await session.execute(
        select(func.coalesce(func.sum(TaskDispatch.points_awarded), 0))
        .join(Application, TaskDispatch.application_id == Application.id)
        .where(Application.team_id == team_id)
    )
    adjustment_result = await session.execute(
        select(func.coalesce(func.sum(TeamPointAdjustment.points), 0)).where(
            TeamPointAdjustment.team_id == team_id,
            TeamPointAdjustment.applied_at.is_not(None),
        )
    )
    return (
        (dispatch_result.scalar_one() or 0)
        + (personal_result.scalar_one() or 0)
        + (adjustment_result.scalar_one() or 0)
    )


async def add_point_adjustment(
    session: AsyncSession,
    *,
    team_id: int,
    points: int,
    reason: str,
    admin_user_id: int,
    send_at: dt.datetime,
    applied_at: dt.datetime | None,
    notify_scope: str,
    participant_id: int | None,
) -> TeamPointAdjustment:
    adjustment = TeamPointAdjustment(
        team_id=team_id,
        points=points,
        reason=reason,
        admin_user_id=admin_user_id,
        send_at=send_at,
        applied_at=applied_at,
        notify_scope=notify_scope,
        participant_id=participant_id,
    )
    session.add(adjustment)
    await session.flush()
    return adjustment


async def list_pending_point_adjustments(
    session: AsyncSession, now: dt.datetime
) -> list[TeamPointAdjustment]:
    result = await session.execute(
        select(TeamPointAdjustment).where(
            TeamPointAdjustment.applied_at.is_(None), TeamPointAdjustment.send_at <= now
        )
    )
    return list(result.scalars().all())


async def apply_point_adjustment(
    session: AsyncSession, adjustment: TeamPointAdjustment, applied_at: dt.datetime
) -> None:
    adjustment.applied_at = applied_at
    await session.flush()


async def resolve_adjustment_contacts(
    session: AsyncSession, adjustment: TeamPointAdjustment
) -> list[tuple[int, str | None]]:
    """Кого уведомлять — вычисляется заново по notify_scope/participant_id, а не
    на момент планирования (тот же приём, что и resolve_broadcast_contacts)."""
    if adjustment.notify_scope == "none":
        return []
    if adjustment.notify_scope == "participant":
        if adjustment.participant_id is None:
            return []
        result = await session.execute(
            select(User.telegram_id, User.language)
            .join(Application, Application.user_id == User.id)
            .where(Application.id == adjustment.participant_id)
        )
        return list(result.tuples())
    return await list_team_member_contacts(session, adjustment.team_id)


async def cancel_point_adjustment(session: AsyncSession, adjustment: TeamPointAdjustment) -> None:
    """Отменяет ещё не применённую (applied_at IS NULL) запланированную
    корректировку — удаляет её целиком, вызывающий код обязан проверить
    applied_at перед вызовом."""
    await session.delete(adjustment)


async def get_point_adjustment(
    session: AsyncSession, adjustment_id: int
) -> TeamPointAdjustment | None:
    return await session.get(TeamPointAdjustment, adjustment_id)


async def update_point_adjustment(
    adjustment: TeamPointAdjustment,
    *,
    points: int,
    reason: str,
    send_at: dt.datetime | None = None,
    notify_scope: str | None = None,
    participant_id: int | None = None,
) -> None:
    """Правит уже созданную корректировку — например, координатор ошибся в числе
    баллов или тексте. Счёт команды пересчитывается сам при следующем чтении
    (get_team_score суммирует построчно, отдельного кеша нет). Текущие значения
    (points/reason) сохраняются в previous_versions ДО перезаписи, чтобы в
    админке была видна и исходная версия, а не только последняя. send_at/
    notify_scope/participant_id — только для ещё не применённой (applied_at
    IS NULL) корректировки, поэтому передаются отдельно и необязательны."""
    history_entry: dict[str, object] = {
        "points": adjustment.points,
        "reason": adjustment.reason,
        "edited_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    adjustment.previous_versions = [*(adjustment.previous_versions or []), history_entry]
    adjustment.points = points
    adjustment.reason = reason
    if send_at is not None:
        adjustment.send_at = send_at
    if notify_scope is not None:
        adjustment.notify_scope = notify_scope
        adjustment.participant_id = participant_id


async def list_point_adjustments(session: AsyncSession, team_id: int) -> list[TeamPointAdjustment]:
    result = await session.execute(
        select(TeamPointAdjustment)
        .where(TeamPointAdjustment.team_id == team_id)
        .options(selectinload(TeamPointAdjustment.admin_user))
        .order_by(TeamPointAdjustment.id.desc())
    )
    return list(result.scalars().all())
