from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.keyboards.rules import RULES_CALLBACK
from src.db.repositories.user_repository import get_or_create_user

router = Router(name="rules")


@router.callback_query(F.data == RULES_CALLBACK)
async def on_show_rules(callback: CallbackQuery, db_session: AsyncSession) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return
    user = await get_or_create_user(db_session, callback.from_user.id, callback.from_user.username)
    await callback.message.answer(t(resolve_lang(user.language), "rules_full"))


@router.message(Command("rules"))
async def cmd_rules(message: Message, db_session: AsyncSession) -> None:
    """Пункт меню «Правила для участников» — чтобы вернуться к тексту правил,
    отправленному один раз сразу после регистрации (см. handlers/registration.py)."""
    if message.from_user is None:
        return
    user = await get_or_create_user(db_session, message.from_user.id, message.from_user.username)
    await message.answer(t(resolve_lang(user.language), "rules_full"))
