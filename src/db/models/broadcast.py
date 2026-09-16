from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.admin_user import AdminUser


class Broadcast(Base, TimestampMixin):
    """Одна рассылка из /broadcast — хранится, чтобы можно было посмотреть историю
    и отозвать сообщения, если админ ошибся в тексте или аудитории. Может быть
    отправлена сразу (send_at = момент создания, sent_at выставляется в том же
    запросе) или отложена на будущее (send_at в будущем, sent_at NULL, пока крон
    send_scheduled_broadcasts её не заберёт и не разошлёт)."""

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)
    # Человекочитаемое описание аудитории на момент отправки (например, "Команда
    # «Дельта»") — не ссылка на команду/заявку, чтобы переименование или удаление
    # не искажало историю задним числом.
    audience_label: Mapped[str] = mapped_column(String(150))
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"))

    # Структурные поля аудитории (в отличие от audience_label выше) — нужны, чтобы
    # у отложенной рассылки крон мог заново вычислить актуальных получателей в
    # момент фактической отправки, а не на момент планирования.
    audience: Mapped[str] = mapped_column(String(20), default="all", server_default="all")
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"))

    send_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    # NULL — ещё не отправлена (ждёт своего send_at, см. send_scheduled_broadcasts).
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # Фото или видео к рассылке (как у Task) — взаимоисключающие, уходит вместе с
    # текстом как caption (bot.send_photo/send_video) вместо обычного send_message.
    attachment_photo_key: Mapped[str | None] = mapped_column(String(255))
    attachment_video_key: Mapped[str | None] = mapped_column(String(255))

    admin_user: Mapped[AdminUser] = relationship()


class BroadcastMessage(Base, TimestampMixin):
    """Telegram chat_id + message_id одного сообщения одной рассылки."""

    __tablename__ = "broadcast_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id"), index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
