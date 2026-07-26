from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin

DEFAULT_PENALTY_POINTS = 2


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)

    # когда воркер должен разослать задание всем командам разом. NULL — задание не на
    # фиксированное время, а по триггеру (см. trigger_task_id) — отправляется каждой
    # команде индивидуально, когда наступит её момент.
    send_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # если задано — это задание не рассылается по расписанию, а отправляется команде
    # через trigger_delay_minutes после того, как ЭТА ЖЕ команда выполнит trigger_task_id.
    # Раз на команду: идемпотентность обеспечивает уникальность (task_id, team_id) в
    # TaskDispatch — планировщик просто проверяет, есть ли уже диспетч, прежде чем создать.
    trigger_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    trigger_delay_minutes: Mapped[int | None] = mapped_column(Integer)

    # к какому моменту нужно уложиться — если не успели, штраф penalty_points.
    # Для "заданий дня" (is_daily=True) вычисляется как конец суток send_at админ-панелью
    # при создании, а не в рантайме. NULL — дедлайна нет вовсе, штраф никогда не начисляется
    # (list_dispatches_needing_penalty_check естественно отфильтровывает NULL в сравнении).
    deadline_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_daily: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    penalty_points: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_PENALTY_POINTS, server_default=str(DEFAULT_PENALTY_POINTS)
    )

    # воркер выставляет после реальной рассылки/после применения штрафов — идемпотентность
    # cron-джобов для заданий с фиксированным временем отправки (dispatched не используется
    # для заданий-триггеров — там идемпотентность на уровне TaskDispatch по команде)
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    penalties_applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Фото или видео, приложенное к заданию в админке — уходит вместе с текстом при
    # рассылке (bot.send_photo/send_video с текстом задания как caption вместо обычного
    # send_message). Взаимоисключающие: приложить можно либо фото, либо видео.
    attachment_photo_key: Mapped[str | None] = mapped_column(String(255))
    attachment_video_key: Mapped[str | None] = mapped_column(String(255))

    trigger_task: Mapped[Task | None] = relationship(remote_side=[id])
