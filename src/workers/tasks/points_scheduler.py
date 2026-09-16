import datetime as dt
from typing import Any

from aiogram import Bot

from src.bot.notify import notify_user
from src.core.logging import get_logger
from src.db.repositories.team_repository import (
    apply_point_adjustment,
    list_pending_point_adjustments,
    resolve_adjustment_contacts,
)
from src.db.session import async_session_factory

logger = get_logger(__name__)


async def apply_scheduled_point_adjustments(ctx: dict[str, Any]) -> None:
    """Cron-джоб: корректировки баллов, отложенные на будущее (TeamPointAdjustment.
    send_at в будущем на момент создания) — применяются к счёту команды и, если
    notify_scope != "none", уведомляют получателей прямо сейчас, а не на момент
    планирования (см. resolve_adjustment_contacts)."""
    bot: Bot = ctx["bot"]
    now = dt.datetime.now(dt.UTC)

    async with async_session_factory() as session:
        pending = await list_pending_point_adjustments(session, now)
        for adjustment in pending:
            await apply_point_adjustment(session, adjustment, now)
            contacts = await resolve_adjustment_contacts(session, adjustment)
            for telegram_id, _language in contacts:
                await notify_user(bot, telegram_id, adjustment.reason)
            logger.info(
                "scheduled_point_adjustment_applied",
                adjustment_id=adjustment.id,
                team_id=adjustment.team_id,
                points=adjustment.points,
                recipients=len(contacts),
            )
        await session.commit()
