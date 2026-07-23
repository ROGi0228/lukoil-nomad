import datetime as dt

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.keyboards.tasks import TASK_DONE_CALLBACK_PREFIX
from src.bot.notify import notify_user
from src.core.logging import get_logger
from src.db.repositories.task_repository import (
    count_completed_dispatches_for_task,
    get_dispatch,
    get_task,
    points_for_completion_rank,
)
from src.db.repositories.team_repository import list_team_member_contacts
from src.db.repositories.user_repository import get_or_create_user

router = Router(name="tasks")
logger = get_logger(__name__)


@router.callback_query(F.data.startswith(TASK_DONE_CALLBACK_PREFIX))
async def on_task_done(callback: CallbackQuery, db_session: AsyncSession, bot: Bot) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        return

    await callback.answer()

    dispatch_id = int(callback.data.removeprefix(TASK_DONE_CALLBACK_PREFIX))
    dispatch = await get_dispatch(db_session, dispatch_id)
    if dispatch is None:
        return

    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    lang = resolve_lang(user.language)

    task = await get_task(db_session, dispatch.task_id)
    if task is None:
        return

    if dispatch.penalty_applied:
        await callback.message.answer(t(lang, "task_deadline_passed"))
        return
    if dispatch.completed_at is not None:
        await callback.message.answer(t(lang, "task_already_done"))
        return

    now = dt.datetime.now(dt.UTC)
    if task.deadline_at is not None and now > task.deadline_at:
        await callback.message.answer(t(lang, "task_deadline_passed"))
        return

    rank = await count_completed_dispatches_for_task(db_session, task.id)
    points = points_for_completion_rank(rank)

    dispatch.completed_at = now
    dispatch.completed_by_user_id = user.id
    dispatch.points_awarded = points
    team_id = dispatch.team_id
    await db_session.commit()

    contacts = await list_team_member_contacts(db_session, team_id)
    for telegram_id, language in contacts:
        member_lang = resolve_lang(language)
        if points > 0:
            text = t(
                member_lang,
                "task_completed_ranked",
                title=task.title,
                place=rank + 1,
                points=points,
            )
        else:
            text = t(member_lang, "task_completed_no_bonus", title=task.title)
        await notify_user(bot, telegram_id, text)
