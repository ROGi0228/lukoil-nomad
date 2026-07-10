from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.bot.keyboards.start import start_keyboard
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


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=start_keyboard(settings))
