import datetime as dt

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base, TimestampMixin

DEFAULT_PENALTY_POINTS = 2


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)

    # когда воркер должен разослать задание командам
    send_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
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
    # cron-джобов: не разослать/не оштрафовать дважды
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    penalties_applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
