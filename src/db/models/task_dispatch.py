from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.task import Task
    from src.db.models.task_submission_item import TaskSubmissionItem
    from src.db.models.team import Team


class TaskDispatch(Base, TimestampMixin):
    """Доставка одного Task одной Team — ровно одна строка на пару (task, team),
    здесь же фиксируется выполнение и начисленные баллы."""

    __tablename__ = "task_dispatches"
    __table_args__ = (UniqueConstraint("task_id", "team_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)

    sent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # +5/+3/+1 за 1/2/3-е место по скорости, 0 — уложились, но не в тройке,
    # -penalty_points — просрочили дедлайн. NULL, пока не наступило ни то ни другое.
    points_awarded: Mapped[int | None] = mapped_column(Integer)
    penalty_applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Идемпотентность напоминания за REMINDER_MINUTES_BEFORE до дедлайна — чтобы cron не
    # слал его повторно на каждом цикле, пока команда наконец не сдаст.
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    task: Mapped[Task] = relationship()
    team: Mapped[Team] = relationship()
    # Подтверждение сдачи — одно или несколько вложений (фото/видео/текст). Без этого
    # "первый нажавший" ничего не значит: кнопка не требует реального выполнения
    # задания, только клика. Рейтинг фиксируется по первому вложению, но команда может
    # прислать ещё, пока не нажмёт «Готово» (см. src/bot/handlers/tasks.py).
    submission_items: Mapped[list[TaskSubmissionItem]] = relationship(
        back_populates="dispatch", order_by="TaskSubmissionItem.id"
    )
