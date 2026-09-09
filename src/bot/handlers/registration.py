from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.keyboards.registration import (
    PDN_ACCEPT_CALLBACK,
    PDN_DECLINE_CALLBACK,
    PDN_RESTART_CALLBACK,
    pdn_consent_keyboard,
)
from src.bot.keyboards.rules import rules_keyboard
from src.bot.keyboards.start import (
    JOIN_CALLBACK,
    SUBSCRIBE_CHECK_CALLBACK,
    registration_closed_keyboard,
    subscribe_keyboard,
)
from src.bot.states.registration_states import RegistrationStates
from src.bot.utils.subscription import is_subscribed_to_channel
from src.bot.utils.validators import validate_full_name
from src.core.config import Settings
from src.core.logging import get_logger
from src.db.repositories.app_settings_repository import is_registration_closed
from src.db.repositories.application_repository import (
    create_application,
    get_application_by_user_id,
)
from src.db.repositories.user_repository import get_or_create_user

router = Router(name="registration")
logger = get_logger(__name__)


async def _proceed_to_registration(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.update_data(lang=lang)
    await state.set_state(RegistrationStates.waiting_full_name)
    await callback.message.answer(t(lang, "subscribed_ask_full_name"))  # type: ignore[union-attr]


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
        if existing.team is None:
            await callback.message.answer(t(lang, "status_registered_no_team"))
        else:
            await callback.message.answer(
                t(lang, "status_registered_with_team", team_name=existing.team.name)
            )
        return

    if await is_registration_closed(db_session):
        await callback.message.answer(
            t(lang, "registration_closed"), reply_markup=registration_closed_keyboard(lang, settings)
        )
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
    await state.set_state(RegistrationStates.waiting_pdn_consent)
    await message.answer(
        t(lang, "confirm_data", full_name=full_name), reply_markup=pdn_consent_keyboard(lang)
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
        await create_application(db_session, user_id=user.id, full_name=data["full_name"])
    except IntegrityError:
        await db_session.rollback()
        await state.clear()
        await callback.message.answer(t(lang, "already_registered"))
        return

    await state.clear()
    await callback.message.answer(t(lang, "registration_complete"))
    await callback.message.answer(t(lang, "rules_intro"), reply_markup=rules_keyboard(lang))


@router.callback_query(RegistrationStates.waiting_pdn_consent, F.data == PDN_DECLINE_CALLBACK)
async def on_consent_decline(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = resolve_lang(data.get("lang"))
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.answer(t(lang, "pdn_declined"))


@router.callback_query(RegistrationStates.waiting_pdn_consent, F.data == PDN_RESTART_CALLBACK)
async def on_consent_restart(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = resolve_lang(data.get("lang"))
    await callback.answer()
    if callback.message is None:
        return

    await state.set_data({"lang": lang})
    await state.set_state(RegistrationStates.waiting_full_name)
    await callback.message.answer(t(lang, "ask_full_name"))
