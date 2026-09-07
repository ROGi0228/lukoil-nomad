import datetime as dt

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.task import Task
from src.db.models.task_dispatch import TaskDispatch
from src.db.models.task_dispatch_message import TaskDispatchMessage
from src.db.models.task_submission_item import TaskSubmissionItem
from src.shared.enums import TaskCriterion


async def create_task(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    send_at: dt.datetime | None,
    deadline_at: dt.datetime | None,
    is_daily: bool,
    penalty_points: int,
    criterion: TaskCriterion,
    pass_points: int,
    rank_points: list[int],
    short_code: str | None = None,
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
        criterion=criterion,
        pass_points=pass_points,
        rank_points=rank_points,
        short_code=short_code,
        trigger_task_id=trigger_task_id,
        trigger_delay_minutes=trigger_delay_minutes,
    )
    session.add(task)
    await session.flush()
    return task


async def update_task(
    task: Task,
    *,
    title: str,
    description: str,
    send_at: dt.datetime | None,
    deadline_at: dt.datetime | None,
    is_daily: bool,
    penalty_points: int,
    criterion: TaskCriterion,
    pass_points: int,
    rank_points: list[int],
    trigger_task_id: int | None,
    trigger_delay_minutes: int | None,
    short_code: str | None = None,
) -> None:
    """Правит уже созданное задание — например, если админ ошибся в дате/дедлайне.
    Уже отправленные сообщения при этом не меняются, только дальнейшее поведение
    (напоминания/штраф считаются по новому дедлайну, будущие триггер-рассылки — по
    новым trigger_task_id/trigger_delay_minutes)."""
    task.title = title
    task.description = description
    task.send_at = send_at
    task.deadline_at = deadline_at
    task.is_daily = is_daily
    task.penalty_points = penalty_points
    task.criterion = criterion
    task.pass_points = pass_points
    task.rank_points = rank_points
    task.trigger_task_id = trigger_task_id
    task.trigger_delay_minutes = trigger_delay_minutes
    task.short_code = short_code


def set_task_attachment(
    task: Task, *, photo_key: str | None = None, video_key: str | None = None
) -> None:
    """Прикрепляет/заменяет/убирает фото или видео задания. Вызывается отдельно от
    create_task/update_task, так как для create ключ в S3 строится из task.id, а он
    появляется только после первого flush."""
    task.attachment_photo_key = photo_key
    task.attachment_video_key = video_key


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
        # Глобальные миссии не сдаются через бота вообще (нет кнопки) — их некому
        # "просрочить" автоматически, баллы всегда проставляет админ вручную.
        .where(Task.criterion != TaskCriterion.GLOBAL_MISSION)
        .options(selectinload(TaskDispatch.task))
    )
    return list(result.scalars().all())


async def list_dispatches_needing_deadline_reminder(
    session: AsyncSession, now: dt.datetime, minutes_before: int
) -> list[TaskDispatch]:
    """Ещё не сданные и не оштрафованные диспетчи, которым скоро (через
    minutes_before минут или меньше) наступит дедлайн — и напоминание ещё не слали."""
    threshold = now + dt.timedelta(minutes=minutes_before)
    result = await session.execute(
        select(TaskDispatch)
        .join(Task, TaskDispatch.task_id == Task.id)
        .where(TaskDispatch.completed_at.is_(None))
        .where(TaskDispatch.penalty_applied.is_(False))
        .where(TaskDispatch.reminder_sent.is_(False))
        .where(Task.deadline_at.is_not(None))
        .where(Task.deadline_at <= threshold)
        .where(Task.deadline_at > now)
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


async def claim_dispatch(
    session: AsyncSession, *, dispatch_id: int, user_id: int, now: dt.datetime, points: int | None
) -> bool:
    """Атомарно (одним UPDATE ... WHERE completed_at IS NULL) помечает диспетч
    выполненным — единственный источник истины о том, кто из команды сдал задание
    первым. Без этого два участника одной команды, приславшие вложение почти
    одновременно, оба прошли бы проверку "ещё не сдано" по устаревшему прочитанному
    состоянию и получили бы баллы дважды. Возвращает True, если именно этот вызов
    выиграл гонку (rowcount=1), False — если кто-то уже успел сдать первым."""
    result = await session.execute(
        update(TaskDispatch)
        .where(TaskDispatch.id == dispatch_id, TaskDispatch.completed_at.is_(None))
        .values(completed_at=now, completed_by_user_id=user_id, points_awarded=points)
    )
    return result.rowcount == 1


async def claim_submission_slot(session: AsyncSession, *, dispatch_id: int, user_id: int) -> bool:
    """Атомарно застолбливает право собирать вложения к сдаче за одним участником
    команды — место/баллы решаются только по нажатию «Готово» (claim_dispatch), это
    же поле лишь фиксирует, кто ведёт текущую сдачу, чтобы двое из команды не начали
    параллельно и независимо прикреплять вложения к одному диспетчу. Возвращает True,
    если именно этот вызов выиграл гонку за первое вложение."""
    result = await session.execute(
        update(TaskDispatch)
        .where(
            TaskDispatch.id == dispatch_id,
            TaskDispatch.completed_by_user_id.is_(None),
            TaskDispatch.completed_at.is_(None),
        )
        .values(completed_by_user_id=user_id)
    )
    return result.rowcount == 1


async def count_completed_dispatches_for_task(session: AsyncSession, task_id: int) -> int:
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.task_id == task_id)
        .where(TaskDispatch.completed_at.is_not(None))
    )
    return len(result.scalars().all())


def points_for_completion_rank(rank_zero_based: int, rank_points: list[int]) -> int:
    """rank_zero_based=0 — первая завершившая команда, 1 — вторая, и т.д."""
    if rank_zero_based < len(rank_points):
        return rank_points[rank_zero_based]
    return 0


async def set_dispatch_points(session: AsyncSession, *, dispatch: TaskDispatch, points: int) -> None:
    """criterion=MANUAL/GLOBAL_MISSION — админ проставляет баллы за диспетч вручную
    (голосование по лайкам, секундомер координатора на месте, финальный зачёт
    глобальных миссий и т.п.), а не автоматика по факту/порядку сдачи. Для
    глобальных миссий это единственный момент, когда completed_at вообще
    выставляется — сдачи через бота у них нет."""
    if dispatch.completed_at is None:
        dispatch.completed_at = dt.datetime.now(dt.UTC)
    dispatch.points_awarded = points
    await session.flush()


async def list_active_global_mission_dispatches(
    session: AsyncSession, now: dt.datetime
) -> list[TaskDispatch]:
    """Глобальные миссии (Критерий №3), ещё не оценённые админом и (если есть
    дедлайн) не просроченные — для ежедневного напоминания командам."""
    result = await session.execute(
        select(TaskDispatch)
        .join(Task, TaskDispatch.task_id == Task.id)
        .where(Task.criterion == TaskCriterion.GLOBAL_MISSION)
        .where(TaskDispatch.points_awarded.is_(None))
        .where(or_(Task.deadline_at.is_(None), Task.deadline_at > now))
        .options(selectinload(TaskDispatch.task))
    )
    return list(result.scalars().all())


async def list_dispatches_for_task(session: AsyncSession, task_id: int) -> list[TaskDispatch]:
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.task_id == task_id)
        .options(selectinload(TaskDispatch.team), selectinload(TaskDispatch.submission_items))
        .order_by(TaskDispatch.completed_at.is_(None), TaskDispatch.completed_at)
    )
    return list(result.scalars().all())


async def list_dispatches_with_short_code(session: AsyncSession) -> list[TaskDispatch]:
    """Все диспетчи заданий с заполненным short_code, по всем командам разом — сырьё
    для таблицы /leaderboard (см. src/bot/leaderboard_table.py): одна выборка вместо
    запроса на каждую команду, колонки таблицы общие для всех строк."""
    result = await session.execute(
        select(TaskDispatch)
        .join(Task, TaskDispatch.task_id == Task.id)
        .where(Task.short_code.is_not(None))
        .options(selectinload(TaskDispatch.task))
    )
    return list(result.scalars().all())


async def list_dispatches_for_team(session: AsyncSession, team_id: int) -> list[TaskDispatch]:
    """Все задания, полученные этой командой — для команды бота «Мои задания»."""
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.team_id == team_id)
        .options(selectinload(TaskDispatch.task))
        .order_by(TaskDispatch.sent_at.desc())
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


async def add_dispatch_message(
    session: AsyncSession, *, dispatch_id: int, telegram_id: int, message_id: int
) -> TaskDispatchMessage:
    record = TaskDispatchMessage(
        dispatch_id=dispatch_id, telegram_id=telegram_id, message_id=message_id
    )
    session.add(record)
    await session.flush()
    return record


async def list_dispatch_messages_for_task(
    session: AsyncSession, task_id: int
) -> list[TaskDispatchMessage]:
    """Все сохранённые (chat_id, message_id) уведомлений о рассылке этого задания —
    чтобы можно было отозвать их, если админ ошибся в данных задания."""
    result = await session.execute(
        select(TaskDispatchMessage)
        .join(TaskDispatch, TaskDispatchMessage.dispatch_id == TaskDispatch.id)
        .where(TaskDispatch.task_id == task_id)
    )
    return list(result.scalars().all())
