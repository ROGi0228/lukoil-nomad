from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.i18n import Lang, t
from src.core.config import Settings

JOIN_CALLBACK = "start_registration"
LANG_RU_CALLBACK = "lang_ru"
LANG_KK_CALLBACK = "lang_kk"
SUBSCRIBE_CHECK_CALLBACK = "subscribe_check"


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("ru", "btn_lang_ru"), callback_data=LANG_RU_CALLBACK),
                InlineKeyboardButton(text=t("kk", "btn_lang_kk"), callback_data=LANG_KK_CALLBACK),
            ]
        ]
    )


def start_keyboard(lang: Lang, settings: Settings) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=t(lang, "btn_join"), callback_data=JOIN_CALLBACK)]
    ]
    if settings.news_channel_url:
        buttons.append(
            [InlineKeyboardButton(text=t(lang, "btn_channel"), url=settings.news_channel_url)]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subscribe_keyboard(lang: Lang, settings: Settings) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if settings.news_channel_url:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_subscribe_channel"), url=settings.news_channel_url
                )
            ]
        )
    if settings.instagram_url:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_subscribe_instagram"), url=settings.instagram_url
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text=t(lang, "btn_subscribed"), callback_data=SUBSCRIBE_CHECK_CALLBACK)]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
