import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.task import Task
from src.db.models.task_dispatch import TaskDispatch
from src.db.models.task_submission_item import TaskSubmissionItem

# 1-е/2-е/3-е место по скорости выполнения — индекс списка = (место - 1)
COMPLETION_RANK_POINTS = (5, 3, 1)


async def create_task(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    send_at: dt.datetime | None,
    deadline_at: dt.datetime | None,
    is_daily: bool,
    penalty_points: int,
    trigger_task_id: int | None = None,
    trigger_delay_minutes: int | None = None,
) -> Task:
    task = Task(
        title=title,
        description=description,
        send_at=send_at,
        deadline_at=deadline_at,
        is_daily=is_daily,
        penalty_points=penalty_points,
        trigger_task_id=trigger_task_id,
        trigger_delay_minutes=trigger_delay_minutes,
    )
    session.add(task)
    await session.flush()
    return task


async def get_task(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id, options=[selectinload(Task.trigger_task)])


async def list_tasks(session: AsyncSession) -> list[Task]:
    result = await session.execute(
        select(Task).options(selectinload(Task.trigger_task)).order_by(Task.id.desc())
    )
    return list(result.scalars().all())


async def list_due_tasks_for_dispatch(session: AsyncSession, now: dt.datetime) -> list[Task]:
    """Задания с фиксированным временем отправки (без триггера), готовые к рассылке всем командам сразу."""
    result = await session.execute(
        select(Task)
        .where(Task.trigger_task_id.is_(None))
        .where(Task.dispatched.is_(False))
        .where(Task.send_at <= now)
    )
    return list(result.scalars().all())


async def list_trigger_based_tasks(session: AsyncSession) -> list[Task]:
    """Задания, которые отправляются команде через N минут после того, как ЭТА ЖЕ
    команда выполнит другое (trigger_task_id) задание — не по общему расписанию."""
    result = await session.execute(select(Task).where(Task.trigger_task_id.is_not(None)))
    return list(result.scalars().all())


async def list_completed_dispatches_for_task(
    session: AsyncSession, task_id: int
) -> list[TaskDispatch]:
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.task_id == task_id)
        .where(TaskDispatch.completed_at.is_not(None))
    )
    return list(result.scalars().all())


async def get_dispatch_for_team(
    session: AsyncSession, task_id: int, team_id: int
) -> TaskDispatch | None:
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.task_id == task_id)
        .where(TaskDispatch.team_id == team_id)
    )
    return result.scalar_one_or_none()


async def list_dispatches_needing_penalty_check(
    session: AsyncSession, now: dt.datetime
) -> list[TaskDispatch]:
    result = await session.execute(
        select(TaskDispatch)
        .join(Task, TaskDispatch.task_id == Task.id)
        .where(TaskDispatch.completed_at.is_(None))
        .where(TaskDispatch.penalty_applied.is_(False))
        .where(Task.deadline_at <= now)
        .options(selectinload(TaskDispatch.task))
    )
    return list(result.scalars().all())


async def create_dispatch(
    session: AsyncSession, *, task_id: int, team_id: int, sent_at: dt.datetime
) -> TaskDispatch:
    dispatch = TaskDispatch(task_id=task_id, team_id=team_id, sent_at=sent_at)
    session.add(dispatch)
    await session.flush()
    return dispatch


async def get_dispatch(session: AsyncSession, dispatch_id: int) -> TaskDispatch | None:
    return await session.get(TaskDispatch, dispatch_id)


async def count_completed_dispatches_for_task(session: AsyncSession, task_id: int) -> int:
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.task_id == task_id)
        .where(TaskDispatch.completed_at.is_not(None))
    )
    return len(result.scalars().all())


def points_for_completion_rank(rank_zero_based: int) -> int:
    """rank_zero_based=0 — первая завершившая команда, 1 — вторая, и т.д."""
    if rank_zero_based < len(COMPLETION_RANK_POINTS):
        return COMPLETION_RANK_POINTS[rank_zero_based]
    return 0


async def list_dispatches_for_task(session: AsyncSession, task_id: int) -> list[TaskDispatch]:
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.task_id == task_id)
        .options(selectinload(TaskDispatch.team), selectinload(TaskDispatch.submission_items))
        .order_by(TaskDispatch.completed_at.is_(None), TaskDispatch.completed_at)
    )
    return list(result.scalars().all())


async def add_submission_item(
    session: AsyncSession,
    *,
    dispatch_id: int,
    photo_key: str | None = None,
    video_key: str | None = None,
    text: str | None = None,
) -> TaskSubmissionItem:
    item = TaskSubmissionItem(
        dispatch_id=dispatch_id, photo_key=photo_key, video_key=video_key, text=text
    )
    session.add(item)
    await session.flush()
    return item


async def count_submission_items(session: AsyncSession, dispatch_id: int) -> int:
    result = await session.execute(
        select(TaskSubmissionItem).where(TaskSubmissionItem.dispatch_id == dispatch_id)
    )
    return len(result.scalars().all())
