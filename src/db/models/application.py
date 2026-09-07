from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.team import Team
    from src.db.models.user import User


class Application(Base, TimestampMixin):
    """Регистрация участника. Без отбора (Фаза 14) заявка — это просто анкета:
    существование строки уже означает «зарегистрирован», team_id NULL/не NULL
    различает «ещё не в команде» и «в команде». Кроме ФИО ничего не собирается
    (Фаза 17) — телефон не нужен, задания приходят через сам Telegram-бот; город
    не нужен для механики экспедиции. Защита от повторной регистрации — только
    unique(user_id): один Telegram-аккаунт может подать анкету один раз."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    full_name: Mapped[str] = mapped_column(String(150))
    pdn_consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # команда (Фаза 12/14) — членство в команде хранится только на заявке,
    # отдельной таблицы связей нет, так как участник состоит максимум в одной команде
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))

    user: Mapped[User] = relationship(back_populates="application")
    team: Mapped[Team | None] = relationship(back_populates="members")
