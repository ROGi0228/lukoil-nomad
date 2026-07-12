from aiogram import Bot

from src.core.logging import get_logger

logger = get_logger(__name__)


async def notify_user(bot: Bot, telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(telegram_id, text)
    except Exception:
        logger.exception("notify_user_failed", telegram_id=telegram_id)
