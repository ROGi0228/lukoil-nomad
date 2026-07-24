import datetime as dt

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.keyboards.tasks import (
    TASK_DONE_CALLBACK_PREFIX,
    TASK_SUBMISSION_DONE_CALLBACK,
    task_submission_done_keyboard,
)
from src.bot.notify import notify_user
from src.bot.states.task_states import TaskSubmissionStates
from src.core.logging import get_logger
from src.db.models.task import Task
from src.db.models.task_dispatch import TaskDispatch
from src.db.repositories.task_repository import (
    add_submission_item,
    count_completed_dispatches_for_task,
    count_submission_items,
    get_dispatch,
    get_task,
    points_for_completion_rank,
)
from src.db.repositories.team_repository import list_team_member_contacts
from src.db.repositories.user_repository import get_or_create_user
from src.services.storage.s3_storage import S3Storage

router = Router(name="tasks")
logger = get_logger(__name__)


def _is_deadline_open(task: Task, now: dt.datetime) -> bool:
    return not (task.deadline_at is not None and now > task.deadline_at)


async def _finalize_completion(
    db_session: AsyncSession,
    bot: Bot,
    dispatch: TaskDispatch,
    task: Task,
    user_id: int,
    now: dt.datetime,
) -> None:
    rank = await count_completed_dispatches_for_task(db_session, task.id)
    points = points_for_completion_rank(rank)

    dispatch.completed_at = now
    dispatch.completed_by_user_id = user_id
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


@router.callback_query(F.data.startswith(TASK_DONE_CALLBACK_PREFIX))
async def on_task_done(
    callback: CallbackQuery, db_session: AsyncSession, state: FSMContext
) -> None:
    """Кнопка не завершает задание сама по себе — иначе "кто первый нажал" не значит
    ничего, задание можно вообще не делать. Она лишь переводит в режим сдачи: команда
    присылает реальное подтверждение (фото/видео/текст, можно несколько), рейтинг
    считается по моменту получения первого вложения."""
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

    now = dt.datetime.now(dt.UTC)
    if dispatch.penalty_applied:
        await callback.message.answer(t(lang, "task_deadline_passed"))
        return
    if dispatch.completed_at is not None:
        await callback.message.answer(t(lang, "task_already_done"))
        return
    if not _is_deadline_open(task, now):
        await callback.message.answer(t(lang, "task_deadline_passed"))
        return

    await state.update_data(dispatch_id=dispatch_id)
    await state.set_state(TaskSubmissionStates.waiting_submission)
    await callback.message.answer(t(lang, "task_submission_prompt", title=task.title))


@router.message(TaskSubmissionStates.waiting_submission, F.photo | F.video | F.text)
async def on_task_submission(
    message: Message,
    state: FSMContext,
    db_session: AsyncSession,
    storage: S3Storage,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    lang = resolve_lang(user.language)

    data = await state.get_data()
    dispatch_id = data.get("dispatch_id")
    if dispatch_id is None:
        await state.clear()
        return

    dispatch = await get_dispatch(db_session, dispatch_id)
    task = await get_task(db_session, dispatch.task_id) if dispatch is not None else None
    if dispatch is None or task is None:
        await state.clear()
        return

    now = dt.datetime.now(dt.UTC)
    is_first_item = dispatch.completed_at is None

    if is_first_item:
        if dispatch.penalty_applied or not _is_deadline_open(task, now):
            await state.clear()
            await message.answer(t(lang, "task_deadline_passed"))
            return
    elif dispatch.completed_by_user_id != user.id:
        # Кто-то другой из команды уже сдал это задание, пока мы были в процессе — не
        # добавляем вложение к чужой сдаче.
        await state.clear()
        await message.answer(t(lang, "task_already_done"))
        return

    photo_key: str | None = None
    video_key: str | None = None
    text_answer: str | None = None

    if message.photo:
        file_id = message.photo[-1].file_id
        buffer = await bot.download(file_id)
        if buffer is not None:
            photo_key = f"task_submissions/{dispatch.id}/{file_id}.jpg"
            await storage.upload(photo_key, buffer.read(), content_type="image/jpeg")
    elif message.video:
        file_id = message.video.file_id
        buffer = await bot.download(file_id)
        if buffer is not None:
            video_key = f"task_submissions/{dispatch.id}/{file_id}.mp4"
            await storage.upload(video_key, buffer.read(), content_type="video/mp4")
    elif message.text:
        text_answer = message.text

    await add_submission_item(
        db_session,
        dispatch_id=dispatch.id,
        photo_key=photo_key,
        video_key=video_key,
        text=text_answer,
    )
    await db_session.commit()

    if is_first_item:
        await _finalize_completion(db_session, bot, dispatch, task, user.id, now)
        await message.answer(
            t(lang, "task_submission_add_more"), reply_markup=task_submission_done_keyboard(lang)
        )
    else:
        count = await count_submission_items(db_session, dispatch.id)
        await message.answer(
            t(lang, "task_submission_item_added", count=count),
            reply_markup=task_submission_done_keyboard(lang),
        )


@router.callback_query(
    TaskSubmissionStates.waiting_submission, F.data == TASK_SUBMISSION_DONE_CALLBACK
)
async def on_task_submission_done(
    callback: CallbackQuery, db_session: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()

    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    lang = resolve_lang(user.language)

    data = await state.get_data()
    dispatch_id = data.get("dispatch_id")
    await state.clear()
    if dispatch_id is None:
        return

    count = await count_submission_items(db_session, dispatch_id)
    await callback.message.answer(t(lang, "task_submission_done", count=count))


@router.message(TaskSubmissionStates.waiting_submission)
async def on_task_submission_wrong_content(message: Message, db_session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    await message.answer(t(resolve_lang(user.language), "task_submission_wrong_content"))
