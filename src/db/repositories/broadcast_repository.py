import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.broadcast import Broadcast, BroadcastMessage
from src.db.repositories.application_repository import (
    get_application_contact,
    list_all_applications_contacts,
    list_all_team_members_contacts,
)
from src.db.repositories.team_repository import list_team_member_contacts


async def create_broadcast(
    session: AsyncSession,
    *,
    message: str,
    audience_label: str,
    admin_user_id: int,
    audience: str,
    team_id: int | None,
    participant_id: int | None,
    send_at: dt.datetime,
    sent_at: dt.datetime | None,
) -> Broadcast:
    broadcast = Broadcast(
        message=message,
        audience_label=audience_label,
        admin_user_id=admin_user_id,
        audience=audience,
        team_id=team_id,
        participant_id=participant_id,
        send_at=send_at,
        sent_at=sent_at,
    )
    session.add(broadcast)
    await session.flush()
    return broadcast


def set_broadcast_attachment(
    broadcast: Broadcast, *, photo_key: str | None = None, video_key: str | None = None
) -> None:
    """Прикрепляет/заменяет/убирает фото или видео рассылки. Отдельно от
    create_broadcast, так как ключ в S3 строится из broadcast.id, а он появляется
    только после первого flush (см. set_task_attachment — тот же приём)."""
    broadcast.attachment_photo_key = photo_key
    broadcast.attachment_video_key = video_key


async def resolve_broadcast_contacts(
    session: AsyncSession, *, audience: str, team_id: int | None, participant_id: int | None
) -> list[tuple[int, str | None]]:
    """Получатели рассылки — вычисляется заново по сохранённым структурным полям
    (не audience_label), поэтому для отложенной рассылки крон видит актуальный
    состав на момент фактической отправки, а не на момент планирования."""
    if audience == "team":
        if team_id is None:
            return []
        return await list_team_member_contacts(session, team_id)
    if audience == "participant":
        if participant_id is None:
            return []
        contact = await get_application_contact(session, participant_id)
        return [contact] if contact else []
    if audience == "teams":
        return await list_all_team_members_contacts(session)
    return await list_all_applications_contacts(session)


async def list_pending_broadcasts(session: AsyncSession, now: dt.datetime) -> list[Broadcast]:
    result = await session.execute(
        select(Broadcast).where(Broadcast.sent_at.is_(None), Broadcast.send_at <= now)
    )
    return list(result.scalars().all())


async def mark_broadcast_sent(session: AsyncSession, broadcast: Broadcast, sent_at: dt.datetime) -> None:
    broadcast.sent_at = sent_at


async def update_broadcast(
    broadcast: Broadcast,
    *,
    message: str,
    audience_label: str,
    audience: str,
    team_id: int | None,
    participant_id: int | None,
    send_at: dt.datetime,
) -> None:
    """Правит ещё не отправленную (sent_at IS NULL) запланированную рассылку —
    вызывающий код обязан проверить это перед вызовом, здесь не перепроверяется.
    Вложение правится отдельно, через set_broadcast_attachment (см. там же)."""
    broadcast.message = message
    broadcast.audience_label = audience_label
    broadcast.audience = audience
    broadcast.team_id = team_id
    broadcast.participant_id = participant_id
    broadcast.send_at = send_at


async def add_broadcast_message(
    session: AsyncSession, *, broadcast_id: int, telegram_id: int, message_id: int
) -> BroadcastMessage:
    record = BroadcastMessage(
        broadcast_id=broadcast_id, telegram_id=telegram_id, message_id=message_id
    )
    session.add(record)
    await session.flush()
    return record


async def list_broadcasts(session: AsyncSession, limit: int = 20) -> list[Broadcast]:
    result = await session.execute(
        select(Broadcast)
        .options(selectinload(Broadcast.admin_user))
        .order_by(Broadcast.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_broadcast(session: AsyncSession, broadcast_id: int) -> Broadcast | None:
    return await session.get(Broadcast, broadcast_id)


async def list_broadcast_messages(
    session: AsyncSession, broadcast_id: int
) -> list[BroadcastMessage]:
    result = await session.execute(
        select(BroadcastMessage).where(BroadcastMessage.broadcast_id == broadcast_id)
    )
    return list(result.scalars().all())


async def count_broadcast_messages(session: AsyncSession, broadcast_id: int) -> int:
    return len(await list_broadcast_messages(session, broadcast_id))
