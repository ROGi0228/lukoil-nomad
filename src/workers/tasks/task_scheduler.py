import datetime as dt
from typing import Any

from aiogram import Bot

from src.bot.i18n import resolve_lang, t
from src.bot.keyboards.tasks import task_dispatch_keyboard
from src.bot.notify import notify_user
from src.core.logging import get_logger
from src.db.repositories.task_repository import (
    create_dispatch,
    list_dispatches_needing_penalty_check,
    list_due_tasks_for_dispatch,
)
from src.db.repositories.team_repository import list_all_team_ids, list_team_member_contacts
from src.db.session import async_session_factory

logger = get_logger(__name__)


async def dispatch_due_tasks(ctx: dict[str, Any]) -> None:
    """Cron-джоб: рассылает задания, у которых наступило время отправки, всем командам."""
    bot: Bot = ctx["bot"]
    now = dt.datetime.now(dt.UTC)

    async with async_session_factory() as session:
        due_tasks = await list_due_tasks_for_dispatch(session, now)
        for task in due_tasks:
            team_ids = await list_all_team_ids(session)
            for team_id in team_ids:
                dispatch = await create_dispatch(
                    session, task_id=task.id, team_id=team_id, sent_at=now
                )
                contacts = await list_team_member_contacts(session, team_id)
                for telegram_id, language in contacts:
                    lang = resolve_lang(language)
                    if task.deadline_at is not None:
                        text = t(
                            lang,
                            "task_dispatched",
                            title=task.title,
                            description=task.description,
                            deadline=task.deadline_at.astimezone(
                                dt.timezone(dt.timedelta(hours=5))
                            ).strftime("%d.%m.%Y %H:%M"),
                        )
                    else:
                        text = t(
                            lang,
                            "task_dispatched_no_deadline",
                            title=task.title,
                            description=task.description,
                        )
                    try:
                        await bot.send_message(
                            telegram_id, text, reply_markup=task_dispatch_keyboard(lang, dispatch.id)
                        )
                    except Exception:
                        logger.exception(
                            "task_dispatch_notify_failed", telegram_id=telegram_id, task_id=task.id
                        )
            task.dispatched = True
        await session.commit()


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
            contacts = await list_team_member_contacts(session, dispatch.team_id)
            for telegram_id, language in contacts:
                lang = resolve_lang(language)
                text = t(lang, "task_penalty", title=task.title, points=task.penalty_points)
                await notify_user(bot, telegram_id, text)
        await session.commit()
