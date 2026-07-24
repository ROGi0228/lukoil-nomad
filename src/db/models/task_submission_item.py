from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.task_dispatch import TaskDispatch


class TaskSubmissionItem(Base, TimestampMixin):
    """Одно вложение к сдаче задания — команда может прислать несколько (несколько
    фото/видео, или текстовый ответ) в рамках одной сдачи. Ровно одно из трёх полей
    заполнено, в зависимости от того, что прислали."""

    __tablename__ = "task_submission_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("task_dispatches.id"), index=True)

    photo_key: Mapped[str | None] = mapped_column(String(255))
    video_key: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(Text)

    dispatch: Mapped[TaskDispatch] = relationship(back_populates="submission_items")
