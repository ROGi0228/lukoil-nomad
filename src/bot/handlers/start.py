from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.start import JOIN_CALLBACK, start_keyboard
from src.core.config import Settings
from src.core.logging import get_logger

router = Router(name="start")
logger = get_logger(__name__)

# ПЛЕЙСХОЛДЕР: заменить на финальный текст, когда заказчик пришлёт бренд-материалы (см. PROJECT_PLAN.md)
WELCOME_TEXT = (
    "<b>Nomad Lukoil</b>\n\n"
    "[ПЛЕЙСХОЛДЕР] Добро пожаловать в проект Nomad Lukoil — автопробег для тех, "
    "кто готов к настоящему приключению.\n\n"
    "<b>О путешествии:</b> [ПЛЕЙСХОЛДЕР] здесь будет описание маршрута, дат и формата поездки.\n\n"
    "<b>Медийные участники:</b> [ПЛЕЙСХОЛДЕР] здесь появится информация об участниках-амбассадорах проекта.\n\n"
    "Нажмите «Принять участие», чтобы начать регистрацию."
)

REGISTRATION_NOT_READY_TEXT = (
    "Регистрация откроется в ближайшее время — этот шаг появится в одном из следующих обновлений бота."
)


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=start_keyboard(settings))


@router.callback_query(F.data == JOIN_CALLBACK)
async def on_start_registration(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(REGISTRATION_NOT_READY_TEXT)
