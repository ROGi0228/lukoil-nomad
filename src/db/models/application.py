from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin
from src.shared.enums import ApplicationStatus, SelectionStage

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
    # номер ВУ (поле 5 бланка, формат "AF 977776")
    document_number: Mapped[str | None] = mapped_column(String(50), unique=True)
    # ЖСН/IIN (поле 4d) — государственный идентификатор человека, не документа:
    # ловит повторную регистрацию даже если у человека новый номер ВУ
    document_iin: Mapped[str | None] = mapped_column(String(12), unique=True, index=True)
    document_expiry_date: Mapped[dt.date | None] = mapped_column(Date)
    # сырой ответ OCR-провайдера + распарсенные поля — для аудита и разбора спорных случаев
    ocr_raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # список сработавших эвристик (fio_mismatch, expired, tamper_suspected, ...) для карточки модератора
    verification_flags: Mapped[list[str] | None] = mapped_column(JSONB)
    video_key: Mapped[str | None] = mapped_column(String(255))
    # присваивается при одобрении, формат "NOMAD_001" — см. applications.py:approve_application
    participant_number: Mapped[str | None] = mapped_column(String(20), unique=True)

    # NULL — ещё не участвует ни в каком отборе (только что одобрен). Отдельно от
    # status: голосование идёт поверх уже одобренных заявок, не часть пайплайна модерации.
    selection_stage: Mapped[SelectionStage | None] = mapped_column(
        SQLEnum(
            SelectionStage,
            native_enum=False,
            validate_strings=True,
            length=30,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
    )
    # проставляется вручную в админ-панели — блогер проходит обычную регистрацию, но
    # не обязан доходить до прав/видео, чтобы попасть в команду (Фаза 12)
    is_blogger: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    user: Mapped[User] = relationship(back_populates="application")
