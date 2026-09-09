from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.i18n import Lang, t

RULES_CALLBACK = "show_rules"


def rules_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_read_rules"), callback_data=RULES_CALLBACK)]]
    )
