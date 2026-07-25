from aiogram import Bot
from aiogram.types import Message

from src.core.logging import get_logger

logger = get_logger(__name__)


async def notify_user(bot: Bot, telegram_id: int, text: str) -> Message | None:
    try:
        return await bot.send_message(telegram_id, text)
    except Exception:
        logger.exception("notify_user_failed", telegram_id=telegram_id)
        return None


async def try_delete_message(bot: Bot, telegram_id: int, message_id: int) -> bool:
    """Telegram может отказать по многим причинам (сообщение старше 48 часов, чат
    недоступен и т.п.) — это не повод прерывать удаление остальных, поэтому здесь
    просто False вместо исключения."""
    try:
        await bot.delete_message(telegram_id, message_id)
        return True
    except Exception:
        logger.exception("delete_message_failed", telegram_id=telegram_id, message_id=message_id)
        return False
