from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.i18n import Lang, t

TASK_DONE_CALLBACK_PREFIX = "task_done:"
TASK_SUBMISSION_DONE_CALLBACK = "task_submission_done"


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


def task_submission_done_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    """Показывается после первого вложения — задание уже засчитано командой, но можно
    прислать ещё фото/видео/текст к этой же сдаче, пока не нажали «Готово»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_task_submission_done"),
                    callback_data=TASK_SUBMISSION_DONE_CALLBACK,
                )
            ]
        ]
    )
