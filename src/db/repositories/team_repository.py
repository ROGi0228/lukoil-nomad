from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.application import Application
from src.db.models.task_dispatch import TaskDispatch
from src.db.models.team import Team
from src.db.models.user import User
from src.shared.enums import SelectionStage


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


async def list_available_winners(session: AsyncSession) -> list[Application]:
    """Победители (Фаза 11), ещё не состоящие ни в одной команде."""
    result = await session.execute(
        select(Application)
        .where(Application.selection_stage == SelectionStage.WINNER)
        .where(Application.team_id.is_(None))
        .order_by(Application.participant_number)
    )
    return list(result.scalars().all())


async def list_available_bloggers(session: AsyncSession) -> list[Application]:
    """Отмеченные блогеры, ещё не состоящие ни в одной команде."""
    result = await session.execute(
        select(Application)
        .where(Application.is_blogger.is_(True))
        .where(Application.team_id.is_(None))
        .order_by(Application.full_name)
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
    result = await session.execute(
        select(func.coalesce(func.sum(TaskDispatch.points_awarded), 0)).where(
            TaskDispatch.team_id == team_id
        )
    )
    return result.scalar_one() or 0
