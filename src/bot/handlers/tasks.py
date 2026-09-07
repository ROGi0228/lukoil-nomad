import asyncio
import datetime as dt

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import Lang, resolve_lang, t
from src.bot.keyboards.tasks import (
    TASK_DONE_CALLBACK_PREFIX,
    TASK_SUBMISSION_DONE_CALLBACK,
    task_submission_done_keyboard,
)
from src.bot.notify import notify_user, try_delete_message
from src.bot.states.task_states import TaskSubmissionStates
from src.bot.utils.validators import MAX_FILE_SIZE_BYTES
from src.core.logging import get_logger
from src.db.models.task import Task
from src.db.models.task_dispatch import TaskDispatch
from src.db.repositories.task_repository import (
    add_submission_item,
    claim_dispatch,
    claim_submission_slot,
    count_completed_dispatches_for_task,
    count_submission_items,
    dispatch_contacts,
    get_dispatch,
    get_task,
    list_dispatch_messages_for_dispatch,
    points_for_completion_rank,
)
from src.db.repositories.user_repository import get_or_create_user
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage
from src.shared.enums import TaskCriterion

router = Router(name="tasks")
logger = get_logger(__name__)

# Сколько ждать после последнего полученного вложения альбома, прежде чем считать
# его законченным и прислать одно итоговое "принято" вместо одного на каждое фото.
ALBUM_ACK_DEBOUNCE_SECONDS = 1.5

# media_group_id -> отложенная задача с итоговым "принято". Один процесс бота,
# поэтому обычный dict в памяти достаточен — переживать перезапуск не нужно.
_pending_album_acks: dict[str, asyncio.Task[None]] = {}


async def _track_cleanup_message(state: FSMContext, message_id: int) -> None:
    """Запоминает id промежуточного служебного сообщения сдачи (подсказка "прикрепите
    вложения", квитанция "Принято... [Готово]"), чтобы удалить его при нажатии
    «Готово» — иначе в чате копятся неактуальные кнопки и подсказки (особенно
    заметно, если вложения присланы несколькими отдельными сообщениями — у каждого
    своя квитанция со своей кнопкой). Список, не одно значение — их может быть
    несколько; в редком случае одновременной записи можно потерять один id
    (не атомарно), тогда одно сообщение просто не удалится — не страшно, это чисто
    косметическая уборка, а не начисление баллов."""
    data = await state.get_data()
    ids: list[int] = list(data.get("cleanup_message_ids", []))
    ids.append(message_id)
    await state.update_data(cleanup_message_ids=ids)


async def _send_submission_ack(bot: Bot, chat_id: int, lang: Lang, dispatch_id: int, state: FSMContext) -> None:
    async with async_session_factory() as session:
        count = await count_submission_items(session, dispatch_id)
    sent = await bot.send_message(
        chat_id,
        t(lang, "task_submission_item_added", count=count),
        reply_markup=task_submission_done_keyboard(lang),
    )
    await _track_cleanup_message(state, sent.message_id)


async def _debounced_album_ack(
    bot: Bot, chat_id: int, lang: Lang, dispatch_id: int, media_group_id: str, state: FSMContext
) -> None:
    try:
        await asyncio.sleep(ALBUM_ACK_DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return
    _pending_album_acks.pop(media_group_id, None)
    await _send_submission_ack(bot, chat_id, lang, dispatch_id, state)


def _ack_submission(
    bot: Bot, message: Message, lang: Lang, dispatch_id: int, state: FSMContext
) -> asyncio.Task[None] | None:
    """Одиночное фото/видео/текст — отвечаем сразу. Альбом (несколько сообщений с
    общим media_group_id, Telegram доставляет их отдельными апдейтами почти
    одновременно) — копим и отвечаем один раз итоговым количеством, а не одним
    сообщением на каждое фото."""
    group_id = message.media_group_id
    if group_id is None:
        return asyncio.create_task(_send_submission_ack(bot, message.chat.id, lang, dispatch_id, state))

    existing = _pending_album_acks.get(group_id)
    if existing is not None and not existing.done():
        existing.cancel()
    task = asyncio.create_task(
        _debounced_album_ack(bot, message.chat.id, lang, dispatch_id, group_id, state)
    )
    _pending_album_acks[group_id] = task
    return task


async def _cleanup_messages(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    for message_id in message_ids:
        await try_delete_message(bot, chat_id, message_id)


def _is_deadline_open(task: Task, now: dt.datetime) -> bool:
    return not (task.deadline_at is not None and now > task.deadline_at)


def _not_a_command(message: Message) -> bool:
    """Команда типа /points, набранная во время сдачи задания, не должна
    засчитываться как текстовый ответ — иначе бот молча "съедал" бы её как
    вложение вместо того, чтобы обработать как обычную команду (F.text у aiogram
    считает командный текст обычным текстом, если явно не исключить его)."""
    return not (message.text and message.text.startswith("/"))


async def _finalize_completion(
    db_session: AsyncSession,
    bot: Bot,
    dispatch: TaskDispatch,
    task: Task,
    user_id: int,
    now: dt.datetime,
) -> bool:
    """Считает баллы и атомарно (claim_dispatch) фиксирует, что задание сдано —
    единственная команда, единственное начисление, даже если несколько участников
    одной команды прислали вложение почти одновременно. Возвращает False, если
    кто-то из команды успел сдать первым буквально между чтением dispatch выше по
    стеку и этим вызовом — тогда баллы уже начислены тем, первым, вызовом."""
    # Ранг обязательно считаем ДО claim_dispatch — иначе повторный подсчёт увидел бы
    # уже отмеченный завершённым текущий диспетч и посчитал бы команду саму за себя,
    # сдвинув место на одну позицию назад для всех.
    rank: int | None = None
    points: int | None
    if task.criterion == TaskCriterion.PASS_FAIL:
        points = task.pass_points
    elif task.criterion == TaskCriterion.SPEED_RANK:
        rank = await count_completed_dispatches_for_task(db_session, task.id)
        points = points_for_completion_rank(rank, task.rank_points)
    else:
        # MANUAL — баллы проставляет админ вручную (см. src/admin_panel/routers/tasks.py)
        points = None

    won = await claim_dispatch(db_session, dispatch_id=dispatch.id, user_id=user_id, now=now, points=points)
    if not won:
        await db_session.commit()
        return False

    dispatch.completed_at = now
    dispatch.completed_by_user_id = user_id
    dispatch.points_awarded = points
    await db_session.commit()

    contacts = await dispatch_contacts(db_session, dispatch)
    for telegram_id, language in contacts:
        member_lang = resolve_lang(language)
        if task.criterion == TaskCriterion.PASS_FAIL:
            text = t(member_lang, "task_completed_pass", title=task.title, points=points)
        elif task.criterion == TaskCriterion.SPEED_RANK:
            assert rank is not None and points is not None
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
        else:
            text = t(member_lang, "task_completed_manual", title=task.title)
        await notify_user(bot, telegram_id, text)

    # Кнопка «Сдать задание» в исходной рассылке этого диспетча (у всех участников
    # команды, не только у того, кто сдавал) теперь бессмысленна — задание уже
    # сдано. Чистим, чтобы не путала команду и не копилась хламом в чате.
    dispatch_messages = await list_dispatch_messages_for_dispatch(db_session, dispatch.id)
    for dispatch_message in dispatch_messages:
        await try_delete_message(bot, dispatch_message.telegram_id, dispatch_message.message_id)
        await db_session.delete(dispatch_message)
    await db_session.commit()

    return True


@router.callback_query(F.data.startswith(TASK_DONE_CALLBACK_PREFIX))
async def on_task_done(
    callback: CallbackQuery, db_session: AsyncSession, state: FSMContext
) -> None:
    """Кнопка не завершает задание сама по себе — иначе "кто первый нажал" не значит
    ничего, задание можно вообще не делать. Она лишь переводит в режим сдачи: команда
    присылает реальное подтверждение (фото/видео/текст, можно несколько) и явно
    нажимает «Готово» — только этот момент фиксирует место в рейтинге и баллы,
    не первое вложение (см. on_task_submission_done)."""
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
    sent = await callback.message.answer(t(lang, "task_submission_prompt", title=task.title))
    await _track_cleanup_message(state, sent.message_id)


@router.message(TaskSubmissionStates.waiting_submission, _not_a_command, F.photo | F.video | F.text)
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

    if dispatch.completed_at is not None:
        # Уже нажали «Готово» раньше (мы сами или, если что-то пошло не так, кто-то
        # ещё) — сдача зафиксирована, поздно добавлять вложения.
        await state.clear()
        await message.answer(t(lang, "task_already_done"))
        return
    if dispatch.penalty_applied or not _is_deadline_open(task, now):
        await state.clear()
        await message.answer(t(lang, "task_deadline_passed"))
        return

    if dispatch.completed_by_user_id is None:
        claimed = await claim_submission_slot(db_session, dispatch_id=dispatch.id, user_id=user.id)
        # Коммитим сразу — иначе строка остаётся заблокированной на всё время
        # скачивания/загрузки вложения ниже, и параллельное сообщение от этого же
        # человека (второе фото, отправленное почти одновременно) будет без нужды
        # ждать эту блокировку, прежде чем увидеть, что победитель — тоже он.
        await db_session.commit()
        if not claimed:
            # Не обязательно "кто-то другой": если один и тот же человек шлёт 2-3
            # вложения почти одновременно (обычный случай — прикрепил сразу
            # несколько фото), они обрабатываются параллельно, и это же сообщение
            # могло проиграть гонку за claim_submission_slot самому себе — первое
            # своё же сообщение просто ещё не успело закоммититься. Перечитываем
            # свежее состояние и смотрим, кто реально победил, прежде чем решать,
            # что сдачу ведёт кто-то посторонний.
            dispatch = await get_dispatch(db_session, dispatch.id)
            if dispatch is None or dispatch.completed_by_user_id != user.id:
                await state.clear()
                await message.answer(t(lang, "task_already_done"))
                return
    elif dispatch.completed_by_user_id != user.id:
        # Кто-то другой из команды уже ведёт сдачу этого задания — не
        # добавляем вложение к чужой сдаче.
        await state.clear()
        await message.answer(t(lang, "task_already_done"))
        return

    if message.video is not None and (message.video.file_size or 0) > MAX_FILE_SIZE_BYTES:
        # 20 МБ — предел скачивания файла через облачный Telegram Bot API. Возвращаемся
        # без изменений состояния — можно прислать видео покороче/сжатое, фото или текст.
        await message.answer(t(lang, "task_submission_file_too_big"))
        return

    photo_key: str | None = None
    video_key: str | None = None
    text_answer: str | None = None

    try:
        if message.photo:
            file_id = message.photo[-1].file_id
            buffer = await bot.download(file_id)
            if buffer is not None:
                photo_key = f"task_submissions/{dispatch.id}/{file_id}.jpg"
                await storage.upload(photo_key, buffer.read(), content_type="image/jpeg")
            # Подпись к фото/видео — тот же текст, что и отдельный текстовый ответ,
            # просто пришедший в одном сообщении с вложением, а не отдельным.
            text_answer = message.caption
        elif message.video:
            file_id = message.video.file_id
            buffer = await bot.download(file_id)
            if buffer is not None:
                video_key = f"task_submissions/{dispatch.id}/{file_id}.mp4"
                await storage.upload(video_key, buffer.read(), content_type="video/mp4")
            text_answer = message.caption
        elif message.text:
            text_answer = message.text
    except Exception:
        logger.exception("task_submission_download_failed", dispatch_id=dispatch.id)
        await message.answer(t(lang, "task_submission_download_failed"))
        return

    await add_submission_item(
        db_session,
        dispatch_id=dispatch.id,
        photo_key=photo_key,
        video_key=video_key,
        text=text_answer,
    )
    await db_session.commit()

    _ack_submission(bot, message, lang, dispatch.id, state)


@router.callback_query(
    TaskSubmissionStates.waiting_submission, F.data == TASK_SUBMISSION_DONE_CALLBACK
)
async def on_task_submission_done(
    callback: CallbackQuery, db_session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    """Именно этот момент — не первое вложение — решает место в рейтинге и баллы
    (см. docstring on_task_done). Команда может прислать сколько угодно фото/видео,
    ничего не начисляется, пока явно не нажата эта кнопка."""
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()

    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    lang = resolve_lang(user.language)

    data = await state.get_data()
    dispatch_id = data.get("dispatch_id")
    # Подсказка "прикрепите вложения" + все квитанции ("Принято... [Готово]"),
    # включая ту, что нажали именно сейчас — свою кнопку добавляем на всякий случай
    # явно, чтобы гонка при записи в state (см. _track_cleanup_message) не оставила
    # несведённой хотя бы её.
    cleanup_message_ids: set[int] = set(data.get("cleanup_message_ids", []))
    cleanup_message_ids.add(callback.message.message_id)
    chat_id = callback.message.chat.id
    await state.clear()
    if dispatch_id is None:
        return

    async def reply(text: str) -> None:
        await _cleanup_messages(bot, chat_id, list(cleanup_message_ids))
        await bot.send_message(chat_id, text)

    dispatch = await get_dispatch(db_session, dispatch_id)
    task = await get_task(db_session, dispatch.task_id) if dispatch is not None else None
    if dispatch is None or task is None:
        return

    count = await count_submission_items(db_session, dispatch.id)
    if count == 0:
        # Нажали «Готово», не прислав ни одного вложения — сдавать нечего.
        await reply(t(lang, "task_submission_nothing_to_finish"))
        return

    if dispatch.completed_at is not None:
        await reply(t(lang, "task_already_done"))
        return

    now = dt.datetime.now(dt.UTC)
    if dispatch.penalty_applied or not _is_deadline_open(task, now):
        await reply(t(lang, "task_deadline_passed"))
        return

    won = await _finalize_completion(db_session, bot, dispatch, task, user.id, now)
    if won:
        await reply(t(lang, "task_submission_done", count=count))
    else:
        # Кто-то другой из команды успел нажать «Готово» одновременно с нами —
        # баллы уже начислены тем вызовом.
        await reply(t(lang, "task_already_done"))


@router.message(TaskSubmissionStates.waiting_submission, _not_a_command)
async def on_task_submission_wrong_content(message: Message, db_session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    await message.answer(t(resolve_lang(user.language), "task_submission_wrong_content"))
