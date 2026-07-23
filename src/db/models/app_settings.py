from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import Base, TimestampMixin


class AppSettings(Base, TimestampMixin):
    """Единственная строка (id=1) с глобальными переключателями проекта."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
