import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from src.core.logging import get_logger

logger = get_logger("bot.update")


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        structlog.contextvars.bind_contextvars(
            user_id=user.id if user else None,
            update_type=event.__class__.__name__,
        )
        started_at = time.monotonic()
        try:
            return await handler(event, data)
        finally:
            logger.info(
                "update_processed",
                duration_ms=round((time.monotonic() - started_at) * 1000, 1),
            )
            structlog.contextvars.clear_contextvars()
