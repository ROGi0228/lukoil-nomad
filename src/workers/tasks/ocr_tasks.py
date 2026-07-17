from typing import Any

from aiogram import Bot
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.fsm_control import set_fsm_state
from src.bot.notify import notify_user
from src.bot.states.document_states import DocumentStates
from src.bot.states.video_states import VideoStates
from src.core.config import get_settings
from src.core.logging import get_logger
from src.db.models.application import Application
from src.db.models.user import User
from src.db.session import async_session_factory
from src.services.antifraud.image_forensics import analyze_image
from src.services.ocr.google_vision import GoogleVisionOCR
from src.services.ocr.parser import ParsedDriverLicense, parse_driver_license
from src.services.storage.s3_storage import S3Storage
from src.services.verification.document_validator import (
    birth_date_from_iin,
    is_expired,
    parse_document_date,
    validate_iin_format,
    validate_license_number,
)
from src.services.verification.fio_matcher import fio_matches
from src.shared.enums import ApplicationStatus

logger = get_logger(__name__)


async def _find_duplicate_document(
    session: AsyncSession, application_id: int, license_number: str | None, iin: str | None
) -> Application | None:
    conditions = []
    if license_number:
        conditions.append(Application.document_number == license_number)
    if iin:
        conditions.append(Application.document_iin == iin)
    if not conditions:
        return None

    result = await session.execute(
        select(Application).where(Application.id != application_id, or_(*conditions))
    )
    return result.scalar_one_or_none()


def _build_ocr_raw_data(raw_text: str, parsed: ParsedDriverLicense) -> dict[str, Any]:
    return {
        "raw_text": raw_text,
        "parsed": {
            "surname": parsed.surname,
            "given_names": parsed.given_names,
            "birth_date": parsed.birth_date,
            "birth_place": parsed.birth_place,
            "issue_date": parsed.issue_date,
            "expiry_date": parsed.expiry_date,
            "issuing_authority": parsed.issuing_authority,
            "iin": parsed.iin,
            "license_number": parsed.license_number,
        },
    }


async def process_document_ocr(ctx: dict[str, Any], application_id: int) -> None:
    settings = get_settings()
    storage = S3Storage(settings)
    bot: Bot = ctx["bot"]

    async with async_session_factory() as session:
        application = await session.get(Application, application_id)
        if application is None:
            logger.warning("ocr_task_application_not_found", application_id=application_id)
            return

        user = await session.get(User, application.user_id)
        if user is None:
            logger.warning("ocr_task_user_not_found", application_id=application_id)
            return

        if application.document_photo_key is None:
            logger.warning("ocr_task_no_photo_key", application_id=application_id)
            return

        try:
            # конструктор тоже внутри try: живой аккаунт Google Vision может быть
            # недоступен (нет креденциалов, квота, сеть) — это тот же класс ошибок,
            # что и сбой самого распознавания, и должен вести к тому же fallback
            image_bytes = await storage.download(application.document_photo_key)
            ocr_provider = GoogleVisionOCR()
            raw_text = await ocr_provider.extract_text(image_bytes)
        except Exception:
            logger.exception("ocr_task_extraction_failed", application_id=application_id)
            application.status = ApplicationStatus.PENDING_DOCUMENT
            await session.commit()
            await set_fsm_state(
                bot, settings.redis_url, user.telegram_id, DocumentStates.waiting_photo
            )
            await notify_user(
                bot,
                user.telegram_id,
                "Не удалось проверить документ — попробуйте прислать фото ещё раз. "
                "Убедитесь, что все поля видны и текст не размыт.",
            )
            return

        parsed = parse_driver_license(raw_text)
        flags: list[str] = []

        license_number = validate_license_number(parsed.license_number or "")
        iin = validate_iin_format(parsed.iin or "")
        expiry_date = parse_document_date(parsed.expiry_date or "")

        if license_number is None:
            flags.append("license_number_not_recognized")
        if iin is None:
            flags.append("iin_not_recognized")
        if expiry_date is None:
            flags.append("expiry_date_not_recognized")
        elif is_expired(expiry_date):
            flags.append("document_expired")

        if iin and parsed.birth_date:
            iin_birth_date = birth_date_from_iin(iin)
            card_birth_date = parse_document_date(parsed.birth_date)
            if iin_birth_date and card_birth_date and iin_birth_date != card_birth_date:
                flags.append("iin_birth_date_mismatch")

        if not fio_matches(application.full_name, parsed.full_name):
            flags.append("fio_mismatch")

        flags.extend(analyze_image(image_bytes))

        duplicate = await _find_duplicate_document(session, application.id, license_number, iin)
        if duplicate is not None:
            flags.append("duplicate_document")

        # Несовпадение ФИО — не "пограничная" эвристика вроде ELA, а однозначный сигнал
        # "это чужой документ": не отправляем на модерацию, а сразу просим прислать своё
        # удостоверение. Не привязываем чужой номер/ИИН к этой заявке — иначе они позже
        # ложно заблокируют настоящего владельца документа проверкой на дубликат.
        fio_mismatch = "fio_mismatch" in flags

        if fio_mismatch:
            application.document_photo_key = None
            application.document_number = None
            application.document_iin = None
            application.document_expiry_date = None
            application.status = ApplicationStatus.PENDING_DOCUMENT
        else:
            application.document_number = None if duplicate is not None else license_number
            application.document_iin = None if duplicate is not None else iin
            application.document_expiry_date = expiry_date
            application.status = (
                ApplicationStatus.DOCUMENT_FLAGGED if flags else ApplicationStatus.PENDING_VIDEO
            )

        application.ocr_raw_data = _build_ocr_raw_data(raw_text, parsed)
        application.verification_flags = flags

        await session.commit()

        if fio_mismatch:
            await set_fsm_state(
                bot, settings.redis_url, user.telegram_id, DocumentStates.waiting_photo
            )
            await notify_user(
                bot,
                user.telegram_id,
                "Похоже, это не ваши водительские права — ФИО на документе не совпадает "
                "с указанным при регистрации. Пришлите, пожалуйста, фото своего "
                "водительского удостоверения.",
            )
        elif duplicate is not None:
            await notify_user(
                bot,
                user.telegram_id,
                "Этот документ уже зарегистрирован в системе под другой заявкой. "
                "Если это ошибка, свяжитесь с администратором проекта.",
            )
        elif flags:
            await notify_user(
                bot,
                user.telegram_id,
                "Документ получен, но потребовалась дополнительная ручная проверка — "
                "мы свяжемся с вами после решения модератора.",
            )
        else:
            await set_fsm_state(
                bot, settings.redis_url, user.telegram_id, VideoStates.waiting_video
            )
            await notify_user(
                bot,
                user.telegram_id,
                "Документ проверен и принят! Пришлите, пожалуйста, видео-визитку "
                "(коротко расскажите о себе на видео). Размер файла — не больше 20 МБ.",
            )
