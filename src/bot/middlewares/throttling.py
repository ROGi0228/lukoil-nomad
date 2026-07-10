from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from redis.asyncio import Redis

# Базовый антиспам-дебаунс на MVP: полноценные лимиты/бэкоффы — Фаза 7.
DEFAULT_COOLDOWN_SECONDS = 0.7


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS) -> None:
        self._redis = redis
        self._cooldown_seconds = cooldown_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None:
            key = f"throttle:{user.id}"
            acquired = await self._redis.set(
                key, "1", nx=True, px=int(self._cooldown_seconds * 1000)
            )
            if not acquired:
                return None
        return await handler(event, data)
