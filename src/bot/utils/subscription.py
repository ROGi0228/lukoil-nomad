from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from src.core.logging import get_logger

logger = get_logger(__name__)

_SUBSCRIBED_STATUSES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.RESTRICTED,
}


async def is_subscribed_to_channel(bot: Bot, channel_username: str, user_id: int) -> bool:
    """Проверяет через getChatMember, состоит ли пользователь в канале.

    Бот должен быть администратором channel_username, иначе Telegram вернёт ошибку.
    Пустой channel_username — проверка подписки отключена (например, локальная
    разработка без настоящего канала) — считаем всех подписанными.
    """
    if not channel_username:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
    except Exception:
        logger.exception("channel_subscription_check_failed", user_id=user_id)
        return False
    return member.status in _SUBSCRIBED_STATUSES
