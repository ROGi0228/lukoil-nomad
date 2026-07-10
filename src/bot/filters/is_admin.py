from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject, User

from src.core.config import Settings


class IsAdmin(BaseFilter):
    async def __call__(
        self, event: TelegramObject, event_from_user: User | None, settings: Settings
    ) -> bool:
        return event_from_user is not None and event_from_user.id in settings.admin_telegram_ids
