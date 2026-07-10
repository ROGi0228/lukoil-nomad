from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
