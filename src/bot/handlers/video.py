from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.states.video_states import VideoStates
from src.bot.utils.video_validators import validate_video_metadata
from src.core.logging import get_logger
from src.db.repositories.application_repository import get_application_by_user_id
from src.db.repositories.user_repository import get_or_create_user
from src.services.storage.s3_storage import S3Storage
from src.shared.enums import ApplicationStatus

router = Router(name="video")
logger = get_logger(__name__)


@router.message(VideoStates.waiting_video, F.video | F.document)
async def on_video(
    message: Message,
    state: FSMContext,
    db_session: AsyncSession,
    storage: S3Storage,
) -> None:
    if message.from_user is None:
        return

    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    lang = resolve_lang(user.language)

    file_id: str | None = None
    duration: int | None = None
    file_size: int | None = None

    if message.video is not None:
        file_id = message.video.file_id
        duration = message.video.duration
        file_size = message.video.file_size
    elif message.document is not None and (message.document.mime_type or "").startswith("video/"):
        file_id = message.document.file_id
        file_size = message.document.file_size

    if file_id is None:
        await message.answer(t(lang, "video_wrong_type"))
        return

    error = validate_video_metadata(duration, file_size, lang)
    if error is not None:
        await message.answer(error)
        return

    application = await get_application_by_user_id(db_session, user.id)
    if application is None:
        await state.clear()
        await message.answer(t(lang, "application_not_found"))
        return

    if message.bot is None:
        return

    buffer = await message.bot.download(file_id)
    if buffer is None:
        await message.answer(t(lang, "video_download_failed"))
        return
    video_bytes = buffer.read()

    key = f"videos/{application.id}/{file_id}.mp4"
    await storage.upload(key, video_bytes, content_type="video/mp4")

    application.video_key = key
    application.status = ApplicationStatus.PENDING_MODERATION
    await db_session.flush()

    await state.clear()
    await message.answer(t(lang, "video_received"))


@router.message(VideoStates.waiting_video)
async def on_video_wrong_content(message: Message, db_session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    await message.answer(t(resolve_lang(user.language), "video_wrong_content_fallback"))
