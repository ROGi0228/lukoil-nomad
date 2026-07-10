from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

PDN_ACCEPT_CALLBACK = "pdn_consent_accept"
PDN_DECLINE_CALLBACK = "pdn_consent_decline"


def pdn_consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Согласен(на)", callback_data=PDN_ACCEPT_CALLBACK),
                InlineKeyboardButton(text="Отказаться", callback_data=PDN_DECLINE_CALLBACK),
            ]
        ]
    )


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
