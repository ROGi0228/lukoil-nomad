from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.i18n import resolve_lang, t
from src.bot.notify import notify_user
from src.db.repositories.application_repository import get_application_contact
from src.db.repositories.team_repository import get_team


async def notify_new_team_members(
    bot: Bot, session: AsyncSession, team_id: int, application_ids: list[int]
) -> None:
    """Уведомляет только что зачисленных в команду участников — название команды и
    с кем они теперь едут. Используется из /teams (создание команды, добавление
    участника) и /applications (назначение команды с карточки заявки) — участников,
    уже состоявших в команде до этого, повторно не уведомляет."""
    team = await get_team(session, team_id)
    if team is None:
        return

    for application_id in application_ids:
        member = next((m for m in team.members if m.id == application_id), None)
        if member is None:
            continue
        contact = await get_application_contact(session, application_id)
        if contact is None:
            continue
        telegram_id, language = contact
        lang = resolve_lang(language)
        teammates = [m.full_name for m in team.members if m.id != application_id]
        if teammates:
            text = t(lang, "team_assigned", team_name=team.name, teammates=", ".join(teammates))
        else:
            text = t(lang, "team_assigned_alone", team_name=team.name)
        await notify_user(bot, telegram_id, text)
