from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import Lang, resolve_lang, t
from src.bot.keyboards.start import (
    LANG_KK_CALLBACK,
    LANG_RU_CALLBACK,
    language_keyboard,
    start_keyboard,
)
from src.core.config import Settings
from src.core.logging import get_logger
from src.db.repositories.user_repository import get_or_create_user

router = Router(name="start")
logger = get_logger(__name__)


def _bilingual_intro_text() -> str:
    return (
        f"{t('ru', 'welcome_intro')}\n\n"
        "— — —\n\n"
        f"{t('kk', 'welcome_intro')}\n\n"
        f"{t('ru', 'choose_language_prompt')} / {t('kk', 'choose_language_prompt')}"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db_session: AsyncSession, settings: Settings) -> None:
    if message.from_user is None:
        return

    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    await db_session.commit()

    if user.language is None:
        await message.answer(_bilingual_intro_text(), reply_markup=language_keyboard())
        return

    lang = resolve_lang(user.language)
    await message.answer(t(lang, "welcome"), reply_markup=start_keyboard(lang, settings))


@router.message(Command("language"))
async def cmd_language(message: Message, db_session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    user.language = None
    await db_session.commit()

    await message.answer(_bilingual_intro_text(), reply_markup=language_keyboard())


@router.callback_query(F.data.in_({LANG_RU_CALLBACK, LANG_KK_CALLBACK}))
async def on_language_selected(
    callback: CallbackQuery, db_session: AsyncSession, settings: Settings
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return

    lang: Lang = "ru" if callback.data == LANG_RU_CALLBACK else "kk"
    user = await get_or_create_user(
        db_session, callback.from_user.id, callback.from_user.username
    )
    user.language = lang
    await db_session.commit()

    await callback.message.answer(t(lang, "welcome"), reply_markup=start_keyboard(lang, settings))
