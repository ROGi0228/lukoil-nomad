from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from arq import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.states.document_states import DocumentStates
from src.core.logging import get_logger
from src.db.repositories.application_repository import get_application_by_user_id
from src.db.repositories.user_repository import get_or_create_user
from src.services.storage.s3_storage import S3Storage
from src.shared.enums import ApplicationStatus

router = Router(name="document")
logger = get_logger(__name__)


@router.message(DocumentStates.waiting_photo, F.photo | F.document)
async def on_document_photo(
    message: Message,
    state: FSMContext,
    db_session: AsyncSession,
    storage: S3Storage,
    arq_pool: ArqRedis,
) -> None:
    if message.from_user is None:
        return

    file_id: str | None = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document is not None and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id

    if file_id is None:
        await message.answer(
            "Пришлите, пожалуйста, именно фото водительского удостоверения "
            "(изображением или файлом-картинкой)."
        )
        return

    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    application = await get_application_by_user_id(db_session, user.id)
    if application is None:
        await state.clear()
        await message.answer("Анкета не найдена. Начните регистрацию заново — /start.")
        return

    if message.bot is None:
        return

    buffer = await message.bot.download(file_id)
    if buffer is None:
        await message.answer("Не удалось загрузить файл, попробуйте прислать фото ещё раз.")
        return
    image_bytes = buffer.read()

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
    await message.answer(
        "Фото получено, документ проверяется — обычно это занимает не больше минуты. "
        "Мы пришлём сообщение, как только проверка завершится."
    )


@router.message(DocumentStates.waiting_photo)
async def on_document_wrong_content(message: Message) -> None:
    await message.answer(
        "Пришлите, пожалуйста, фото водительского удостоверения изображением или файлом-картинкой."
    )
