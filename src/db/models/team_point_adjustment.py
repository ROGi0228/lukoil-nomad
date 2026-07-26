from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.admin_user import AdminUser
    from src.db.models.team import Team


class TeamPointAdjustment(Base, TimestampMixin):
    """Ручная корректировка баллов команды админом — не привязана к конкретному
    заданию (снять ошибочный штраф, начислить бонус и т.п.). Складывается с суммой
    TaskDispatch.points_awarded в get_team_score()."""

    __tablename__ = "team_point_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"))

    team: Mapped[Team] = relationship()
    admin_user: Mapped[AdminUser] = relationship()
