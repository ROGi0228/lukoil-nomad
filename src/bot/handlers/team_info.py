import datetime as dt
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import Lang, resolve_lang, t
from src.bot.keyboards.tasks import task_dispatch_keyboard
from src.bot.leaderboard_table import build_leaderboard_rows, chunk_leaderboard_messages
from src.db.models.application import Application
from src.db.models.task_dispatch import TaskDispatch
from src.db.repositories.application_repository import get_application_by_user_id
from src.db.repositories.task_repository import (
    list_dispatches_for_team,
    list_dispatches_with_short_code,
)
from src.db.repositories.team_repository import get_team_score, list_teams
from src.db.repositories.user_repository import get_or_create_user
from src.shared.enums import TaskCriterion

router = Router(name="team_info")

_ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _format_dt(value: dt.datetime) -> str:
    return value.astimezone(_ALMATY_TZ).strftime("%d.%m.%Y %H:%M")


async def _require_team(
    message: Message, db_session: AsyncSession, lang: Lang, user_id: int
) -> Application | None:
    """Общая проверка для /tasks, /points, /leaderboard — все три команды имеют
    смысл только для участника, уже распределённого в команду."""
    application = await get_application_by_user_id(db_session, user_id)
    if application is None:
        await message.answer(t(lang, "no_application_yet"))
        return None
    if application.team is None:
        await message.answer(t(lang, "status_registered_no_team"))
        return None
    return application


def _is_resolved(dispatch: TaskDispatch) -> bool:
    """Команда уже ничего не может сделать с этим заданием через кнопку — сдано
    (баллы начислены или ждут ручной оценки), дедлайн просрочен, или это глобальная
    миссия (Критерий №3) — у неё в принципе нет кнопки «Сдать», баллы всегда
    проставляет админ вручную в конце. Остальное — ещё можно сдать."""
    return (
        dispatch.completed_at is not None
        or dispatch.penalty_applied
        or dispatch.task.criterion == TaskCriterion.GLOBAL_MISSION
    )


def _resolved_task_line(lang: Lang, dispatch: TaskDispatch) -> str:
    task = dispatch.task
    if task.criterion == TaskCriterion.GLOBAL_MISSION:
        if dispatch.points_awarded is not None:
            return t(lang, "task_line_done_scored", title=task.title, points=dispatch.points_awarded)
        return t(lang, "task_line_global_mission_pending", title=task.title)
    if dispatch.completed_at is not None:
        if dispatch.points_awarded is not None:
            return t(lang, "task_line_done_scored", title=task.title, points=dispatch.points_awarded)
        return t(lang, "task_line_done_pending_score", title=task.title)
    points = dispatch.points_awarded if dispatch.points_awarded is not None else 0
    return t(lang, "task_line_overdue", title=task.title, points=points)


def _pending_task_text(lang: Lang, dispatch: TaskDispatch) -> str:
    task = dispatch.task
    if task.deadline_at is not None:
        return t(
            lang,
            "task_pending_deadline",
            title=task.title,
            description=task.description,
            deadline=_format_dt(task.deadline_at),
        )
    return t(lang, "task_pending_no_deadline", title=task.title, description=task.description)


@router.message(Command("tasks"))
async def cmd_my_tasks(message: Message, db_session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    lang = resolve_lang(user.language)

    application = await _require_team(message, db_session, lang, user.id)
    if application is None or application.team is None:
        return

    dispatches = await list_dispatches_for_team(db_session, application.team.id)
    if not dispatches:
        await message.answer(t(lang, "my_tasks_empty"))
        return

    resolved = [d for d in dispatches if _is_resolved(d)]
    pending = [d for d in dispatches if not _is_resolved(d)]

    if resolved:
        lines = [t(lang, "my_tasks_header", team_name=application.team.name)]
        lines.extend(_resolved_task_line(lang, d) for d in resolved)
        await message.answer("\n".join(lines))

    # Незавершённые задания — отдельным сообщением с кнопкой «Сдать задание» у
    # каждого, той же самой, что приходит при первой рассылке задания (тот же
    # callback_data, тот же обработчик on_task_done в handlers/tasks.py).
    for dispatch in pending:
        await message.answer(
            _pending_task_text(lang, dispatch), reply_markup=task_dispatch_keyboard(lang, dispatch.id)
        )


@router.message(Command("points"))
async def cmd_my_points(message: Message, db_session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    lang = resolve_lang(user.language)

    application = await _require_team(message, db_session, lang, user.id)
    if application is None or application.team is None:
        return

    score = await get_team_score(db_session, application.team.id)
    await message.answer(t(lang, "my_points", team_name=application.team.name, points=score))


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message, db_session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    lang = resolve_lang(user.language)

    application = await _require_team(message, db_session, lang, user.id)
    if application is None or application.team is None:
        return

    teams = await list_teams(db_session)
    if not teams:
        await message.answer(t(lang, "leaderboard_empty"))
        return

    scores = {team.id: await get_team_score(db_session, team.id) for team in teams}
    dispatches = await list_dispatches_with_short_code(db_session)
    formatted = build_leaderboard_rows(
        dispatches=dispatches, teams=teams, scores=scores, own_team_id=application.team.id
    )
    chunks = chunk_leaderboard_messages(formatted)

    # Заголовок — только над первым сообщением, подпись про "*" — только под
    # последним; в обычном случае (один чанк) всё это уходит одним сообщением.
    for i, chunk in enumerate(chunks):
        parts = []
        if i == 0:
            parts.append(t(lang, "leaderboard_header"))
        parts.append(f"<pre>{chunk}</pre>")
        if i == len(chunks) - 1:
            parts.append(t(lang, "leaderboard_own_team_marker"))
        await message.answer("\n".join(parts))
