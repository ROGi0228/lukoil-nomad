from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.i18n import Lang, t

TASK_DONE_CALLBACK_PREFIX = "task_done:"


def task_dispatch_keyboard(lang: Lang, dispatch_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_task_done"),
                    callback_data=f"{TASK_DONE_CALLBACK_PREFIX}{dispatch_id}",
                )
            ]
        ]
    )
