import datetime as dt
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.keyboards.tasks import task_dispatch_keyboard
from src.bot.notify import notify_user, try_delete_message
from src.core.config import get_settings
from src.core.logging import get_logger
from src.db.models.task import Task
from src.db.models.task_dispatch import TaskDispatch
from src.db.repositories.application_repository import list_all_applications
from src.db.repositories.task_repository import (
    add_dispatch_message,
    create_dispatch,
    dispatch_contacts,
    get_dispatch_for_application,
    get_dispatch_for_team,
    list_active_global_mission_dispatches,
    list_completed_dispatches_for_task,
    list_dispatch_messages_for_dispatch,
    list_dispatches_needing_deadline_reminder,
    list_dispatches_needing_penalty_check,
    list_due_tasks_for_dispatch,
    list_trigger_based_tasks,
)
from src.db.repositories.team_repository import list_all_team_ids
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage
from src.shared.enums import TaskCriterion

logger = get_logger(__name__)

# За сколько минут до дедлайна напоминать команде, что задание ещё не сдано.
REMINDER_MINUTES_BEFORE = 15

# Ежедневное напоминание про глобальные миссии (Критерий №3) — 10:00 по Алматы
# (UTC+5, без перехода на летнее время, см. src/admin_panel/display.py).
GLOBAL_MISSION_REMINDER_HOUR_UTC = 5


async def _send_dispatch(
    session: AsyncSession,
    bot: Bot,
    task: Task,
    dispatch: TaskDispatch,
    contacts: list[tuple[int, str | None]],
) -> None:
    attachment_url = None
    if task.attachment_photo_key or task.attachment_video_key:
        storage = S3Storage(get_settings())
        key = task.attachment_photo_key or task.attachment_video_key
        assert key is not None
        attachment_url = await storage.presigned_url(key)

    for telegram_id, language in contacts:
        lang = resolve_lang(language)
        if task.deadline_at is not None:
            text = t(
                lang,
                "task_dispatched",
                title=task.title,
                description=task.description,
                deadline=task.deadline_at.astimezone(dt.timezone(dt.timedelta(hours=5))).strftime(
                    "%d.%m.%Y %H:%M"
                ),
            )
        else:
            text = t(
                lang,
                "task_dispatched_no_deadline",
                title=task.title,
                description=task.description,
            )
        try:
            # Глобальная миссия (Критерий №3) — чисто информационная рассылка, без
            # кнопки «Сдать задание»: сдачи через бота у неё нет, баллы в конце
            # проставляет админ вручную (см. set_dispatch_points).
            keyboard = (
                None
                if task.criterion == TaskCriterion.GLOBAL_MISSION
                else task_dispatch_keyboard(lang, dispatch.id)
            )
            if attachment_url is not None and task.attachment_photo_key:
                sent = await bot.send_photo(
                    telegram_id, photo=attachment_url, caption=text, reply_markup=keyboard
                )
            elif attachment_url is not None and task.attachment_video_key:
                sent = await bot.send_video(
                    telegram_id, video=attachment_url, caption=text, reply_markup=keyboard
                )
            else:
                sent = await bot.send_message(telegram_id, text, reply_markup=keyboard)
            await add_dispatch_message(
                session, dispatch_id=dispatch.id, telegram_id=telegram_id, message_id=sent.message_id
            )
        except Exception:
            logger.exception(
                "task_dispatch_notify_failed", telegram_id=telegram_id, task_id=task.id
            )


async def dispatch_to_team(
    session: AsyncSession, bot: Bot, task: Task, team_id: int, sent_at: dt.datetime
) -> None:
    dispatch = await create_dispatch(session, task_id=task.id, team_id=team_id, sent_at=sent_at)
    contacts = await dispatch_contacts(session, dispatch)
    await _send_dispatch(session, bot, task, dispatch, contacts)


async def dispatch_to_participant(
    session: AsyncSession, bot: Bot, task: Task, application_id: int, sent_at: dt.datetime
) -> None:
    """Личное задание (Task.is_personal) — тот же диспетч/сдача/баллы, что и у
    командного, просто на одного конкретного зарегистрированного участника вместо
    команды (см. TaskDispatch.application_id)."""
    dispatch = await create_dispatch(
        session, task_id=task.id, application_id=application_id, sent_at=sent_at
    )
    contacts = await dispatch_contacts(session, dispatch)
    await _send_dispatch(session, bot, task, dispatch, contacts)


async def dispatch_due_tasks(ctx: dict[str, Any]) -> None:
    """Cron-джоб: рассылает задания с фиксированным временем отправки — всем командам
    сразу, а личные (Task.is_personal) — каждому зарегистрированному участнику лично,
    независимо от того, распределён он в команду или нет."""
    bot: Bot = ctx["bot"]
    now = dt.datetime.now(dt.UTC)

    async with async_session_factory() as session:
        due_tasks = await list_due_tasks_for_dispatch(session, now)
        for task in due_tasks:
            if task.is_personal:
                applications = await list_all_applications(session)
                for application in applications:
                    await dispatch_to_participant(session, bot, task, application.id, now)
            else:
                team_ids = await list_all_team_ids(session)
                for team_id in team_ids:
                    await dispatch_to_team(session, bot, task, team_id, now)
            task.dispatched = True
        await session.commit()


async def dispatch_trigger_based_tasks(ctx: dict[str, Any]) -> None:
    """Cron-джоб: задания-триггеры — получатель получает задание через N минут после
    того, как ОН ЖЕ (команда или, для личных заданий, конкретный участник) выполнит
    другое задание. Идемпотентность — уникальность (task_id, team_id)/(task_id,
    application_id) в TaskDispatch, проверяем перед созданием."""
    bot: Bot = ctx["bot"]
    now = dt.datetime.now(dt.UTC)

    async with async_session_factory() as session:
        trigger_tasks = await list_trigger_based_tasks(session)
        for task in trigger_tasks:
            if task.trigger_task_id is None or task.trigger_delay_minutes is None:
                continue
            completed = await list_completed_dispatches_for_task(session, task.trigger_task_id)
            for trigger_dispatch in completed:
                assert trigger_dispatch.completed_at is not None
                ready_at = trigger_dispatch.completed_at + dt.timedelta(
                    minutes=task.trigger_delay_minutes
                )
                if ready_at > now:
                    continue
                if trigger_dispatch.team_id is not None:
                    existing = await get_dispatch_for_team(session, task.id, trigger_dispatch.team_id)
                    if existing is not None:
                        continue
                    await dispatch_to_team(session, bot, task, trigger_dispatch.team_id, now)
                else:
                    assert trigger_dispatch.application_id is not None
                    existing = await get_dispatch_for_application(
                        session, task.id, trigger_dispatch.application_id
                    )
                    if existing is not None:
                        continue
                    await dispatch_to_participant(
                        session, bot, task, trigger_dispatch.application_id, now
                    )
        await session.commit()


async def send_deadline_reminders(ctx: dict[str, Any]) -> None:
    """Cron-джоб: напоминает командам, ещё не сдавшим задание, что дедлайн скоро —
    за REMINDER_MINUTES_BEFORE минут. Раз на диспетч (reminder_sent — идемпотентность)."""
    bot: Bot = ctx["bot"]
    now = dt.datetime.now(dt.UTC)

    async with async_session_factory() as session:
        due = await list_dispatches_needing_deadline_reminder(session, now, REMINDER_MINUTES_BEFORE)
        for dispatch in due:
            task = dispatch.task
            assert task.deadline_at is not None
            dispatch.reminder_sent = True
            contacts = await dispatch_contacts(session, dispatch)
            for telegram_id, language in contacts:
                lang = resolve_lang(language)
                text = t(
                    lang,
                    "task_deadline_reminder",
                    title=task.title,
                    minutes=REMINDER_MINUTES_BEFORE,
                    deadline=task.deadline_at.astimezone(dt.timezone(dt.timedelta(hours=5))).strftime(
                        "%d.%m.%Y %H:%M"
                    ),
                )
                await notify_user(bot, telegram_id, text)
        await session.commit()


async def send_global_mission_reminders(ctx: dict[str, Any]) -> None:
    """Cron-джоб (раз в день, GLOBAL_MISSION_REMINDER_HOUR_UTC): напоминает командам
    про ещё не оценённые глобальные миссии — они рассылаются один раз в начале и
    живут до финального дедлайна, без кнопки «Сдать», поэтому команде легко про них
    забыть без периодического напоминания."""
    bot: Bot = ctx["bot"]
    now = dt.datetime.now(dt.UTC)

    async with async_session_factory() as session:
        active = await list_active_global_mission_dispatches(session, now)
        for dispatch in active:
            task = dispatch.task
            contacts = await dispatch_contacts(session, dispatch)
            for telegram_id, language in contacts:
                lang = resolve_lang(language)
                text = t(
                    lang, "global_mission_reminder", title=task.title, description=task.description
                )
                await notify_user(bot, telegram_id, text)


async def apply_deadline_penalties(ctx: dict[str, Any]) -> None:
    """Cron-джоб: командам, не уложившимся в дедлайн, начисляет штраф."""
    bot: Bot = ctx["bot"]
    now = dt.datetime.now(dt.UTC)

    async with async_session_factory() as session:
        overdue = await list_dispatches_needing_penalty_check(session, now)
        for dispatch in overdue:
            task = dispatch.task
            dispatch.penalty_applied = True
            dispatch.points_awarded = -task.penalty_points
            contacts = await dispatch_contacts(session, dispatch)
            for telegram_id, language in contacts:
                lang = resolve_lang(language)
                text = t(lang, "task_penalty", title=task.title, points=task.penalty_points)
                await notify_user(bot, telegram_id, text)

            # Кнопка «Сдать задание» в исходной рассылке этого диспетча теперь
            # бессмысленна и просрочена — чистим, как и при успешной сдаче
            # (см. _finalize_completion в src/bot/handlers/tasks.py), чтобы не
            # висела лишним, уже неактуальным сообщением в чате.
            dispatch_messages = await list_dispatch_messages_for_dispatch(session, dispatch.id)
            for dispatch_message in dispatch_messages:
                await try_delete_message(bot, dispatch_message.telegram_id, dispatch_message.message_id)
                await session.delete(dispatch_message)
        await session.commit()
