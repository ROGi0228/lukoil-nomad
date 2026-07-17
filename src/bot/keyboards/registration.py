from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.bot.i18n import Lang, t

PDN_ACCEPT_CALLBACK = "pdn_consent_accept"
PDN_DECLINE_CALLBACK = "pdn_consent_decline"


def pdn_consent_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "btn_pdn_accept"), callback_data=PDN_ACCEPT_CALLBACK),
                InlineKeyboardButton(text=t(lang, "btn_pdn_decline"), callback_data=PDN_DECLINE_CALLBACK),
            ]
        ]
    )


def phone_request_keyboard(lang: Lang) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_send_phone"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
