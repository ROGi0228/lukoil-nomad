from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base, TimestampMixin


class TaskDispatchMessage(Base, TimestampMixin):
    """Telegram chat_id + message_id одного отправленного уведомления о задании —
    без этого бот не может отозвать сообщение, если админ ошибся в данных задания."""

    __tablename__ = "task_dispatch_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("task_dispatches.id"), index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
