import datetime as dt
from typing import Any

from aiogram import Bot

from src.bot.notify import notify_user
from src.core.logging import get_logger
from src.db.repositories.broadcast_repository import (
    add_broadcast_message,
    list_pending_broadcasts,
    mark_broadcast_sent,
    resolve_broadcast_contacts,
)
from src.db.session import async_session_factory

logger = get_logger(__name__)


async def send_scheduled_broadcasts(ctx: dict[str, Any]) -> None:
    """Cron-джоб: рассылки, отложенные на будущее (Broadcast.send_at в будущем на
    момент создания) — получатели вычисляются заново прямо сейчас, а не на момент
    планирования (см. resolve_broadcast_contacts)."""
    bot: Bot = ctx["bot"]
    now = dt.datetime.now(dt.UTC)

    async with async_session_factory() as session:
        pending = await list_pending_broadcasts(session, now)
        for broadcast in pending:
            contacts = await resolve_broadcast_contacts(
                session,
                audience=broadcast.audience,
                team_id=broadcast.team_id,
                participant_id=broadcast.participant_id,
            )
            for telegram_id, _language in contacts:
                sent_message = await notify_user(bot, telegram_id, broadcast.message)
                if sent_message is not None:
                    await add_broadcast_message(
                        session,
                        broadcast_id=broadcast.id,
                        telegram_id=telegram_id,
                        message_id=sent_message.message_id,
                    )
            await mark_broadcast_sent(session, broadcast, now)
            logger.info(
                "scheduled_broadcast_sent", broadcast_id=broadcast.id, recipients=len(contacts)
            )
        await session.commit()
