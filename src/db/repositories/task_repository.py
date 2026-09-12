import datetime as dt

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.task import Task
from src.db.models.task_dispatch import TaskDispatch
from src.db.models.task_dispatch_message import TaskDispatchMessage
from src.db.models.task_submission_item import TaskSubmissionItem
from src.db.repositories.application_repository import get_application_contact
from src.db.repositories.team_repository import list_team_member_contacts
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
    is_personal: bool = False,
    trigger_task_id: int | None = None,
    trigger_delay_minutes: int | None = None,
    team_text_overrides: dict[str, str] | None = None,
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
        is_personal=is_personal,
        trigger_task_id=trigger_task_id,
        trigger_delay_minutes=trigger_delay_minutes,
        team_text_overrides=team_text_overrides,
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
    is_personal: bool = False,
    team_text_overrides: dict[str, str] | None = None,
) -> None:
    """Правит уже созданное задание — например, если админ ошибся в дате/дедлайне.
    Уже отправленные сообщения при этом не меняются, только дальнейшее поведение
    (напоминания/штраф считаются по новому дедлайну, будущие триггер-рассылки — по
    новым trigger_task_id/trigger_delay_minutes). is_personal тоже не трогает уже
    созданные диспетчи — только то, как задание будет разослано в следующий раз."""
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
    task.is_personal = is_personal
    task.team_text_overrides = team_text_overrides


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


async def get_dispatch_for_application(
    session: AsyncSession, task_id: int, application_id: int
) -> TaskDispatch | None:
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.task_id == task_id)
        .where(TaskDispatch.application_id == application_id)
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
        # Глобальные миссии (оба варианта критерия №3) оцениваются жюри вручную по
        # решению, а не штрафуются автоматически за просрочку — правила экспедиции
        # не называют для них конкретный штраф, в отличие от обычных заданий.
        .where(Task.criterion.not_in([TaskCriterion.GLOBAL_MISSION, TaskCriterion.GLOBAL_MISSION_SUBMIT]))
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
    session: AsyncSession,
    *,
    task_id: int,
    sent_at: dt.datetime,
    team_id: int | None = None,
    application_id: int | None = None,
) -> TaskDispatch:
    """Ровно один из team_id/application_id должен быть передан (см.
    ck_task_dispatch_team_xor_application) — команде или лично участнику."""
    dispatch = TaskDispatch(
        task_id=task_id, team_id=team_id, application_id=application_id, sent_at=sent_at
    )
    session.add(dispatch)
    await session.flush()
    return dispatch


async def get_dispatch(session: AsyncSession, dispatch_id: int) -> TaskDispatch | None:
    return await session.get(TaskDispatch, dispatch_id)


async def dispatch_contacts(session: AsyncSession, dispatch: TaskDispatch) -> list[tuple[int, str | None]]:
    """(telegram_id, language) получателей этого диспетча — вся команда для обычного
    задания, один участник для личного (Task.is_personal, dispatch.team_id is None).
    Используется и планировщиком (рассылка), и ботом (уведомление о сдаче) — один
    источник истины на оба случая, чтобы не разойтись при добавлении личных заданий."""
    if dispatch.team_id is not None:
        return await list_team_member_contacts(session, dispatch.team_id)
    assert dispatch.application_id is not None
    contact = await get_application_contact(session, dispatch.application_id)
    return [contact] if contact is not None else []


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


async def list_dispatches_for_task(session: AsyncSession, task_id: int) -> list[TaskDispatch]:
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.task_id == task_id)
        .options(
            selectinload(TaskDispatch.team),
            selectinload(TaskDispatch.application),
            selectinload(TaskDispatch.submission_items),
        )
        .order_by(TaskDispatch.completed_at.is_(None), TaskDispatch.completed_at)
    )
    return list(result.scalars().all())


async def list_dispatches_with_short_code(session: AsyncSession) -> list[TaskDispatch]:
    """Все КОМАНДНЫЕ диспетчи заданий с заполненным short_code, по всем командам
    разом — сырьё для таблицы /leaderboard (см. src/bot/leaderboard_table.py): одна
    выборка вместо запроса на каждую команду, колонки таблицы общие для всех строк.
    Личные задания (team_id IS NULL) сюда не попадают — таблица по смыслу командная,
    личный зачёт не в команду."""
    result = await session.execute(
        select(TaskDispatch)
        .join(Task, TaskDispatch.task_id == Task.id)
        .where(Task.short_code.is_not(None))
        .where(TaskDispatch.team_id.is_not(None))
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


async def list_dispatches_for_application(
    session: AsyncSession, application_id: int
) -> list[TaskDispatch]:
    """Личные задания этого участника (Task.is_personal) — для команды бота «Мои
    задания», доступны и тем, кто ещё не распределён в команду."""
    result = await session.execute(
        select(TaskDispatch)
        .where(TaskDispatch.application_id == application_id)
        .options(selectinload(TaskDispatch.task))
        .order_by(TaskDispatch.sent_at.desc())
    )
    return list(result.scalars().all())


async def delete_dispatches_for_application(session: AsyncSession, application_id: int) -> None:
    """Чистит личные диспетчи участника (task_dispatches.application_id) со всеми
    зависимостями — нужно перед удалением самой заявки, так как на applications.id
    ссылается task_dispatches.application_id."""
    dispatch_ids = (
        (
            await session.execute(
                select(TaskDispatch.id).where(TaskDispatch.application_id == application_id)
            )
        )
        .scalars()
        .all()
    )
    if not dispatch_ids:
        return
    await session.execute(
        delete(TaskSubmissionItem).where(TaskSubmissionItem.dispatch_id.in_(dispatch_ids))
    )
    await session.execute(
        delete(TaskDispatchMessage).where(TaskDispatchMessage.dispatch_id.in_(dispatch_ids))
    )
    await session.execute(delete(TaskDispatch).where(TaskDispatch.id.in_(dispatch_ids)))


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


async def list_dispatch_messages_for_dispatch(
    session: AsyncSession, dispatch_id: int
) -> list[TaskDispatchMessage]:
    """Копии рассылки этого конкретного диспетча у всех участников команды (не всего
    задания у всех команд) — чтобы отозвать их, когда команда сдала задание: кнопка
    «Сдать задание» в них становится неактуальной для всех, не только для того, кто
    нажал «Готово»."""
    result = await session.execute(
        select(TaskDispatchMessage).where(TaskDispatchMessage.dispatch_id == dispatch_id)
    )
    return list(result.scalars().all())
