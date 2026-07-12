from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin
from src.shared.enums import ModerationAction

if TYPE_CHECKING:
    from src.db.models.admin_user import AdminUser


class ModerationLog(Base, TimestampMixin):
    __tablename__ = "moderation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"))

    # values_callable — та же причина, что и в Application.status (Фаза 2): без него
    # SQLAlchemy хранит .name ("APPROVE"), а не .value ("approve").
    action: Mapped[ModerationAction] = mapped_column(
        SQLEnum(
            ModerationAction,
            native_enum=False,
            validate_strings=True,
            length=30,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        )
    )
    reason: Mapped[str | None] = mapped_column(Text)

    admin_user: Mapped[AdminUser] = relationship()
