import fitz
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.keyboards.document import (
    HAS_LICENSE_CALLBACK,
    NO_LICENSE_CALLBACK,
    no_license_keyboard,
)
from src.bot.keyboards.start import registration_closed_keyboard
from src.bot.states.document_states import DocumentStates
from src.core.config import Settings
from src.core.logging import get_logger
from src.db.repositories.app_settings_repository import is_registration_closed
from src.db.repositories.application_repository import get_application_by_user_id
from src.db.repositories.user_repository import get_or_create_user
from src.services.storage.s3_storage import S3Storage
from src.shared.enums import ApplicationStatus

router = Router(name="document")
logger = get_logger(__name__)

# Масштаб рендера PDF-страницы в изображение: PDF по умолчанию рендерится в 72 DPI,
# для мелкого текста на правах этого мало для OCR — 2.5x даёт ~180 DPI.
_PDF_RENDER_SCALE = 2.5


def _render_pdf_first_page_to_jpeg(pdf_bytes: bytes) -> bytes:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        page = pdf.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(_PDF_RENDER_SCALE, _PDF_RENDER_SCALE))
        jpeg_bytes: bytes = pixmap.tobytes("jpeg")
        return jpeg_bytes


@router.message(DocumentStates.waiting_photo, F.photo | F.document)
async def on_document_photo(
    message: Message,
    state: FSMContext,
    db_session: AsyncSession,
    storage: S3Storage,
    arq_pool: ArqRedis,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    lang = resolve_lang(user.language)

    if await is_registration_closed(db_session):
        await state.clear()
        await message.answer(
            t(lang, "registration_closed"), reply_markup=registration_closed_keyboard(lang, settings)
        )
        return

    file_id: str | None = None
    is_pdf = False
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document is not None:
        mime_type = message.document.mime_type or ""
        if mime_type.startswith("image/"):
            file_id = message.document.file_id
        elif mime_type == "application/pdf":
            file_id = message.document.file_id
            is_pdf = True

    if file_id is None:
        await message.answer(t(lang, "document_wrong_type"))
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
        await message.answer(t(lang, "document_download_failed"))
        return
    raw_bytes = buffer.read()

    if is_pdf:
        try:
            image_bytes = _render_pdf_first_page_to_jpeg(raw_bytes)
        except Exception:
            logger.exception("pdf_render_failed", application_id=application.id)
            await message.answer(t(lang, "pdf_parse_failed"))
            return
    else:
        image_bytes = raw_bytes

    key = f"documents/{application.id}/{file_id}.jpg"
    await storage.upload(key, image_bytes, content_type="image/jpeg")

    application.document_photo_key = key
    application.status = ApplicationStatus.PENDING_OCR
    # Явный commit (не flush) обязателен здесь: воркер открывает свою собственную сессию
    # в отдельном процессе и должен увидеть закоммиченные изменения. DbSessionMiddleware
    # коммитит только после возврата хендлера — если положить задачу в очередь раньше,
    # воркер может обработать её и закоммитить свой результат быстрее, чем закоммитится
    # эта транзакция, и более поздний коммит бота молча затрёт результат воркера.
    await db_session.commit()

    await arq_pool.enqueue_job("process_document_ocr", application.id)

    await state.clear()
    await message.answer(t(lang, "document_received_processing"))


@router.message(DocumentStates.waiting_photo)
async def on_document_wrong_content(message: Message, db_session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    await message.answer(t(resolve_lang(user.language), "document_wrong_content_fallback"))


@router.callback_query(DocumentStates.waiting_photo, F.data == NO_LICENSE_CALLBACK)
async def on_no_license(callback: CallbackQuery, db_session: AsyncSession) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return
    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    lang = resolve_lang(user.language)
    await callback.message.answer(t(lang, "no_license_message"), reply_markup=no_license_keyboard(lang))


@router.callback_query(DocumentStates.waiting_photo, F.data == HAS_LICENSE_CALLBACK)
async def on_has_license(callback: CallbackQuery, db_session: AsyncSession) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return
    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    lang = resolve_lang(user.language)
    await callback.message.answer(t(lang, "has_license_ack"))
