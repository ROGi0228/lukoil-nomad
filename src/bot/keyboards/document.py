from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.i18n import Lang, t

NO_LICENSE_CALLBACK = "no_license"
HAS_LICENSE_CALLBACK = "has_license"


def document_request_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_no_license"), callback_data=NO_LICENSE_CALLBACK)]
        ]
    )


def no_license_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_has_license"), callback_data=HAS_LICENSE_CALLBACK)]
        ]
    )
