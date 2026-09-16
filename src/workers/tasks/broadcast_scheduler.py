import datetime as dt
from typing import Any

from aiogram import Bot
from aiogram.types import Message

from src.bot.notify import notify_user
from src.core.config import get_settings
from src.core.logging import get_logger
from src.db.models.broadcast import Broadcast
from src.db.repositories.broadcast_repository import (
    add_broadcast_message,
    list_pending_broadcasts,
    mark_broadcast_sent,
    resolve_broadcast_contacts,
)
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage

logger = get_logger(__name__)


async def send_broadcast_message(
    bot: Bot, storage: S3Storage, broadcast: Broadcast, telegram_id: int
) -> Message | None:
    """Отправляет одно сообщение рассылки — с фото/видео (caption), если к
    рассылке прикреплено вложение, иначе обычным текстом. Общая для крона
    отложенных рассылок и мгновенной отправки из админки (broadcast.py)."""
    try:
        if broadcast.attachment_photo_key:
            url = await storage.presigned_url(broadcast.attachment_photo_key)
            return await bot.send_photo(telegram_id, photo=url, caption=broadcast.message)
        if broadcast.attachment_video_key:
            url = await storage.presigned_url(broadcast.attachment_video_key)
            return await bot.send_video(telegram_id, video=url, caption=broadcast.message)
        return await notify_user(bot, telegram_id, broadcast.message)
    except Exception:
        logger.exception(
            "broadcast_send_failed", telegram_id=telegram_id, broadcast_id=broadcast.id
        )
        return None


async def send_scheduled_broadcasts(ctx: dict[str, Any]) -> None:
    """Cron-джоб: рассылки, отложенные на будущее (Broadcast.send_at в будущем на
    момент создания) — получатели вычисляются заново прямо сейчас, а не на момент
    планирования (см. resolve_broadcast_contacts)."""
    bot: Bot = ctx["bot"]
    storage = S3Storage(get_settings())
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
                sent_message = await send_broadcast_message(bot, storage, broadcast, telegram_id)
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
