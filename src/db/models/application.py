from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin
from src.shared.enums import ApplicationStatus

if TYPE_CHECKING:
    from src.db.models.user import User


class Application(Base, TimestampMixin):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    full_name: Mapped[str] = mapped_column(String(150))
    # unique — защита от повторной регистрации с другого Telegram-аккаунта тем же номером
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    city: Mapped[str] = mapped_column(String(100))

    # native_enum=False: статус храним как VARCHAR + CHECK, а не PG-нативный enum —
    # добавление нового статуса в будущих фазах это обычный ALTER TABLE, а не ALTER TYPE.
    # values_callable обязателен: без него SQLAlchemy хранит .name ("PENDING_DOCUMENT"),
    # а не .value ("pending_document"), который используется во всём остальном коде.
    status: Mapped[ApplicationStatus] = mapped_column(
        SQLEnum(
            ApplicationStatus,
            native_enum=False,
            validate_strings=True,
            length=30,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ApplicationStatus.DRAFT,
        server_default=ApplicationStatus.DRAFT.value,
    )
    pdn_consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # заполняются в Фазе 3/4
    document_photo_key: Mapped[str | None] = mapped_column(String(255))
    document_number: Mapped[str | None] = mapped_column(String(50), unique=True)
    video_key: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="application")
