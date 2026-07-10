from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.core.config import Settings

JOIN_CALLBACK = "start_registration"


def start_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Принять участие", callback_data=JOIN_CALLBACK)]
    ]
    if settings.news_channel_url:
        buttons.append([InlineKeyboardButton(text="Наш канал", url=settings.news_channel_url)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
