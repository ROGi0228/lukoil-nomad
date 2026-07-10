from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.registration import (
    PDN_ACCEPT_CALLBACK,
    PDN_DECLINE_CALLBACK,
    pdn_consent_keyboard,
    phone_request_keyboard,
)
from src.bot.keyboards.start import JOIN_CALLBACK
from src.bot.states.document_states import DocumentStates
from src.bot.states.registration_states import RegistrationStates
from src.bot.utils.validators import normalize_phone, validate_city, validate_full_name
from src.core.logging import get_logger
from src.db.repositories.application_repository import (
    create_application,
    get_application_by_user_id,
)
from src.db.repositories.user_repository import get_or_create_user
from src.shared.enums import ApplicationStatus

router = Router(name="registration")
logger = get_logger(__name__)

_STATUS_MESSAGES: dict[ApplicationStatus, str] = {
    ApplicationStatus.DRAFT: "Ваша регистрация ещё не завершена — начните заново.",
    ApplicationStatus.PENDING_DOCUMENT: (
        "Анкета уже принята. Пришлите, пожалуйста, фото водительского удостоверения."
    ),
    ApplicationStatus.PENDING_OCR: "Ваш документ проверяется, ожидайте.",
    ApplicationStatus.DOCUMENT_FLAGGED: "Ваш документ на дополнительной проверке у модератора.",
    ApplicationStatus.PENDING_VIDEO: "Осталось загрузить видео-визитку.",
    ApplicationStatus.PENDING_MODERATION: "Ваша заявка на модерации, ожидайте решения.",
    ApplicationStatus.REUPLOAD_REQUESTED: "Модератор запросил повторную загрузку материалов.",
    ApplicationStatus.APPROVED: "Ваша заявка уже одобрена!",
    ApplicationStatus.REJECTED: "К сожалению, ваша заявка была отклонена.",
}


@router.callback_query(F.data == JOIN_CALLBACK)
async def on_join(callback: CallbackQuery, state: FSMContext, db_session: AsyncSession) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return

    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    existing = await get_application_by_user_id(db_session, user.id)
    if existing is not None:
        await callback.message.answer(_STATUS_MESSAGES[existing.status])
        if existing.status in (
            ApplicationStatus.PENDING_DOCUMENT,
            ApplicationStatus.REUPLOAD_REQUESTED,
        ):
            await state.set_state(DocumentStates.waiting_photo)
        return

    await state.set_state(RegistrationStates.waiting_full_name)
    await callback.message.answer("Введите ваше ФИО полностью (например: Иванов Иван Иванович):")


@router.message(RegistrationStates.waiting_full_name)
async def on_full_name(message: Message, state: FSMContext) -> None:
    full_name = validate_full_name(message.text or "")
    if full_name is None:
        await message.answer(
            "Не похоже на ФИО. Введите фамилию и имя (можно с отчеством), "
            "используя только буквы, например: Иванов Иван Иванович:"
        )
        return

    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_phone)
    await message.answer(
        "Отправьте номер телефона кнопкой ниже или введите его вручную "
        "(например: +77071234567):",
        reply_markup=phone_request_keyboard(),
    )


@router.message(RegistrationStates.waiting_phone, F.contact)
async def on_phone_contact(message: Message, state: FSMContext) -> None:
    contact = message.contact
    if contact is None or message.from_user is None or contact.user_id != message.from_user.id:
        await message.answer(
            "Пожалуйста, отправьте именно свой номер телефона кнопкой ниже, "
            "либо введите его вручную:"
        )
        return

    phone = normalize_phone(contact.phone_number)
    if phone is None:
        await message.answer(
            "Не удалось распознать номер. Введите его вручную в формате +77071234567:"
        )
        return

    await _save_phone_and_continue(message, state, phone)


@router.message(RegistrationStates.waiting_phone)
async def on_phone_text(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text or "")
    if phone is None:
        await message.answer(
            "Не похоже на номер телефона. Введите номер в формате +77071234567 "
            "или воспользуйтесь кнопкой «Отправить номер телефона»:"
        )
        return

    await _save_phone_and_continue(message, state, phone)


async def _save_phone_and_continue(message: Message, state: FSMContext, phone: str) -> None:
    await state.update_data(phone=phone)
    await state.set_state(RegistrationStates.waiting_city)
    await message.answer("Введите город проживания:", reply_markup=ReplyKeyboardRemove())


@router.message(RegistrationStates.waiting_city)
async def on_city(message: Message, state: FSMContext) -> None:
    city = validate_city(message.text or "")
    if city is None:
        await message.answer(
            "Название города должно содержать от 2 до 100 букв. Введите город ещё раз:"
        )
        return

    await state.update_data(city=city)
    await state.set_state(RegistrationStates.waiting_pdn_consent)
    data = await state.get_data()
    await message.answer(
        "Проверьте данные:\n"
        f"ФИО: {data['full_name']}\n"
        f"Телефон: {data['phone']}\n"
        f"Город: {city}\n\n"
        "Продолжая, вы даёте согласие на обработку персональных данных "
        "для целей участия в проекте.",
        reply_markup=pdn_consent_keyboard(),
    )


@router.callback_query(RegistrationStates.waiting_pdn_consent, F.data == PDN_ACCEPT_CALLBACK)
async def on_consent_accept(
    callback: CallbackQuery, state: FSMContext, db_session: AsyncSession
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return

    data = await state.get_data()
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
        await callback.message.answer(
            "Этот номер телефона уже зарегистрирован в системе. "
            "Если это ошибка, свяжитесь с администратором проекта."
        )
        return

    await state.set_state(DocumentStates.waiting_photo)
    await callback.message.answer(
        "Спасибо! Анкета сохранена. Пришлите, пожалуйста, фото водительского удостоверения "
        "(изображением или файлом-картинкой)."
    )


@router.callback_query(RegistrationStates.waiting_pdn_consent, F.data == PDN_DECLINE_CALLBACK)
async def on_consent_decline(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.answer(
            "Без согласия на обработку персональных данных продолжить регистрацию нельзя. "
            "Вы можете начать заново в любой момент, нажав «Принять участие»."
        )
