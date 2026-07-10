from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.filters.is_admin import IsAdmin

router = Router(name="admin")


@router.message(Command("admin"), IsAdmin())
async def cmd_admin(message: Message) -> None:
    await message.answer("Доступ администратора подтверждён. Очередь модерации появится в Фазе 5.")
