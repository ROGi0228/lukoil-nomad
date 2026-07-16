from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.bot.keyboards.start import start_keyboard
from src.core.config import Settings
from src.core.logging import get_logger

router = Router(name="start")
logger = get_logger(__name__)

# Черновой текст на время разработки — заменить на финальный, когда заказчик пришлёт бренд-материалы
WELCOME_TEXT = (
    "<b>Nomad Lukoil Expedition</b>\n\n"
    "Добро пожаловать в проект Nomad Lukoil Expedition — автопробег для тех, кто готов к "
    "настоящему приключению за рулём. Мы собираем команду водителей, готовых "
    "пройти маршрут вместе, испытать себя и машину и стать частью большой истории.\n\n"
    "<b>О путешествии:</b> экспедиция объединит участников из разных городов в общем "
    "маршруте с испытаниями, остановками и совместными активностями на всём пути.\n\n"
    "<b>Медийные участники:</b> в пробеге примут участие приглашённые медийные лица "
    "и амбассадоры проекта — подробности будут объявлены в канале проекта.\n\n"
    "Нажмите «Принять участие», чтобы начать регистрацию."
)


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=start_keyboard(settings))
