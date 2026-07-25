from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.broadcast import Broadcast, BroadcastMessage


async def create_broadcast(
    session: AsyncSession, *, message: str, audience_label: str, admin_user_id: int
) -> Broadcast:
    broadcast = Broadcast(message=message, audience_label=audience_label, admin_user_id=admin_user_id)
    session.add(broadcast)
    await session.flush()
    return broadcast


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
