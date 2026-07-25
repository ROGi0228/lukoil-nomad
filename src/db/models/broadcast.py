from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.admin_user import AdminUser


class Broadcast(Base, TimestampMixin):
    """Одна рассылка из /broadcast — хранится, чтобы можно было посмотреть историю
    и отозвать сообщения, если админ ошибся в тексте или аудитории."""

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)
    # Человекочитаемое описание аудитории на момент отправки (например, "Команда
    # «Дельта»") — не ссылка на команду/заявку, чтобы переименование или удаление
    # не искажало историю задним числом.
    audience_label: Mapped[str] = mapped_column(String(150))
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"))

    admin_user: Mapped[AdminUser] = relationship()


class BroadcastMessage(Base, TimestampMixin):
    """Telegram chat_id + message_id одного сообщения одной рассылки."""

    __tablename__ = "broadcast_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id"), index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
