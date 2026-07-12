from aiogram import Bot
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis


async def set_fsm_state(bot: Bot, redis_url: str, telegram_id: int, state: State) -> None:
    """Устанавливает FSM-состояние пользователя напрямую из процесса, отличного от
    самого бота (воркер, админ-панель) — минуя FSMContext, который доступен только
    внутри хендлера aiogram. Нужно, когда переход в новое состояние решается вне
    текущего апдейта (итог фоновой OCR-проверки, действие модератора в панели).
    """
    redis_client: Redis = Redis.from_url(redis_url)
    try:
        storage = RedisStorage(redis=redis_client)
        key = StorageKey(bot_id=bot.id, chat_id=telegram_id, user_id=telegram_id)
        await storage.set_state(key, state)
    finally:
        await redis_client.aclose()
