from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.keyboards.registration import (
    PDN_ACCEPT_CALLBACK,
    PDN_DECLINE_CALLBACK,
    pdn_consent_keyboard,
    phone_request_keyboard,
)
from src.bot.keyboards.start import JOIN_CALLBACK, SUBSCRIBE_CHECK_CALLBACK, subscribe_keyboard
from src.bot.states.document_states import DocumentStates
from src.bot.states.registration_states import RegistrationStates
from src.bot.states.video_states import VideoStates
from src.bot.utils.subscription import is_subscribed_to_channel
from src.bot.utils.validators import normalize_phone, validate_city, validate_full_name
from src.core.config import Settings
from src.core.logging import get_logger
from src.db.repositories.application_repository import (
    create_application,
    get_application_by_user_id,
)
from src.db.repositories.user_repository import get_or_create_user
from src.shared.enums import ApplicationStatus

router = Router(name="registration")
logger = get_logger(__name__)

_STATUS_TEXT_KEYS: dict[ApplicationStatus, str] = {
    ApplicationStatus.DRAFT: "status_draft",
    ApplicationStatus.PENDING_DOCUMENT: "status_pending_document",
    ApplicationStatus.PENDING_OCR: "status_pending_ocr",
    ApplicationStatus.DOCUMENT_FLAGGED: "status_document_flagged",
    ApplicationStatus.PENDING_VIDEO: "status_pending_video",
    ApplicationStatus.PENDING_MODERATION: "status_pending_moderation",
    ApplicationStatus.APPROVED: "status_approved",
    ApplicationStatus.REJECTED: "status_rejected",
}


async def _proceed_to_registration(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.update_data(lang=lang)
    await state.set_state(RegistrationStates.waiting_full_name)
    await callback.message.answer(t(lang, "ask_full_name"))  # type: ignore[union-attr]


@router.callback_query(F.data == JOIN_CALLBACK)
async def on_join(
    callback: CallbackQuery,
    state: FSMContext,
    db_session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return

    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    lang = resolve_lang(user.language)
    existing = await get_application_by_user_id(db_session, user.id)
    if existing is not None:
        await callback.message.answer(t(lang, _STATUS_TEXT_KEYS[existing.status]))
        if existing.status == ApplicationStatus.PENDING_DOCUMENT:
            await state.set_state(DocumentStates.waiting_photo)
        elif existing.status == ApplicationStatus.PENDING_VIDEO:
            await state.set_state(VideoStates.waiting_video)
        return

    subscribed = await is_subscribed_to_channel(
        bot, settings.required_channel_username, callback.from_user.id
    )
    if not subscribed:
        await callback.message.answer(
            t(lang, "subscribe_required"), reply_markup=subscribe_keyboard(lang, settings)
        )
        return

    await _proceed_to_registration(callback, state, lang)


@router.callback_query(F.data == SUBSCRIBE_CHECK_CALLBACK)
async def on_subscribe_check(
    callback: CallbackQuery,
    state: FSMContext,
    db_session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return

    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    lang = resolve_lang(user.language)

    subscribed = await is_subscribed_to_channel(
        bot, settings.required_channel_username, callback.from_user.id
    )
    if not subscribed:
        await callback.message.answer(
            t(lang, "subscribe_channel_not_confirmed"),
            reply_markup=subscribe_keyboard(lang, settings),
        )
        return

    await _proceed_to_registration(callback, state, lang)


@router.message(RegistrationStates.waiting_full_name)
async def on_full_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = resolve_lang(data.get("lang"))

    full_name = validate_full_name(message.text or "")
    if full_name is None:
        await message.answer(t(lang, "invalid_full_name"))
        return

    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_phone)
    await message.answer(t(lang, "ask_phone"), reply_markup=phone_request_keyboard(lang))


@router.message(RegistrationStates.waiting_phone, F.contact)
async def on_phone_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = resolve_lang(data.get("lang"))

    contact = message.contact
    if contact is None or message.from_user is None or contact.user_id != message.from_user.id:
        await message.answer(t(lang, "wrong_contact_owner"))
        return

    phone = normalize_phone(contact.phone_number)
    if phone is None:
        await message.answer(t(lang, "phone_parse_failed"))
        return

    await _save_phone_and_continue(message, state, phone, lang)


@router.message(RegistrationStates.waiting_phone)
async def on_phone_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = resolve_lang(data.get("lang"))

    phone = normalize_phone(message.text or "")
    if phone is None:
        await message.answer(t(lang, "invalid_phone_text"))
        return

    await _save_phone_and_continue(message, state, phone, lang)


async def _save_phone_and_continue(
    message: Message, state: FSMContext, phone: str, lang: str
) -> None:
    await state.update_data(phone=phone)
    await state.set_state(RegistrationStates.waiting_city)
    await message.answer(t(lang, "ask_city"), reply_markup=ReplyKeyboardRemove())


@router.message(RegistrationStates.waiting_city)
async def on_city(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = resolve_lang(data.get("lang"))

    city = validate_city(message.text or "")
    if city is None:
        await message.answer(t(lang, "invalid_city"))
        return

    await state.update_data(city=city)
    await state.set_state(RegistrationStates.waiting_pdn_consent)
    data = await state.get_data()
    await message.answer(
        t(
            lang,
            "confirm_data",
            full_name=data["full_name"],
            phone=data["phone"],
            city=city,
        ),
        reply_markup=pdn_consent_keyboard(lang),
    )


@router.callback_query(RegistrationStates.waiting_pdn_consent, F.data == PDN_ACCEPT_CALLBACK)
async def on_consent_accept(
    callback: CallbackQuery, state: FSMContext, db_session: AsyncSession
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return

    data = await state.get_data()
    lang = resolve_lang(data.get("lang"))
    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)

    try:
        await create_application(
            db_session,
            user_id=user.id,
            full_name=data["full_name"],
            phone=data["phone"],
            city=data["city"],
        )
    except IntegrityError:
        await db_session.rollback()
        await state.clear()
        await callback.message.answer(t(lang, "duplicate_phone"))
        return

    await state.set_state(DocumentStates.waiting_photo)
    await callback.message.answer(t(lang, "registration_saved_ask_document"))


@router.callback_query(RegistrationStates.waiting_pdn_consent, F.data == PDN_DECLINE_CALLBACK)
async def on_consent_decline(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = resolve_lang(data.get("lang"))
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.answer(t(lang, "pdn_declined"))
