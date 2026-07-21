import datetime as dt
from zoneinfo import ZoneInfo

from src.shared.enums import ApplicationStatus, ModerationAction

# Клиент в Казахстане (UTC+5, без перехода на летнее время) — все временные метки
# в БД хранятся в UTC (timestamptz), в интерфейсе показываем сразу в местном времени.
DISPLAY_TIMEZONE = ZoneInfo("Asia/Almaty")

STATUS_LABELS: dict[ApplicationStatus, str] = {
    ApplicationStatus.DRAFT: "Черновик",
    ApplicationStatus.PENDING_DOCUMENT: "Ожидает фото ВУ",
    ApplicationStatus.PENDING_OCR: "Проверяется OCR",
    ApplicationStatus.DOCUMENT_FLAGGED: "Требует проверки",
    ApplicationStatus.PENDING_VIDEO: "Ожидает видео",
    ApplicationStatus.PENDING_MODERATION: "На модерации",
    ApplicationStatus.APPROVED: "Одобрено",
    ApplicationStatus.REJECTED: "Отклонено",
}

# CSS modifier suffix (e.g. "status-badge--{value}") used to colour-code statuses
# consistently across the dashboard cards, table and detail page.
STATUS_CSS_CLASS: dict[ApplicationStatus, str] = {
    ApplicationStatus.DRAFT: "neutral",
    ApplicationStatus.PENDING_DOCUMENT: "waiting",
    ApplicationStatus.PENDING_OCR: "waiting",
    ApplicationStatus.DOCUMENT_FLAGGED: "flagged",
    ApplicationStatus.PENDING_VIDEO: "waiting",
    ApplicationStatus.PENDING_MODERATION: "waiting",
    ApplicationStatus.APPROVED: "approved",
    ApplicationStatus.REJECTED: "rejected",
}

FLAG_LABELS: dict[str, str] = {
    "license_number_not_recognized": "Номер ВУ не распознан",
    "iin_not_recognized": "ИИН не распознан",
    "expiry_date_not_recognized": "Срок действия не распознан",
    "document_expired": "Истёк срок действия",
    "iin_birth_date_mismatch": "Дата рождения не совпадает с ИИН",
    "fio_mismatch": "ФИО не совпадает",
    "duplicate_document": "Документ уже зарегистрирован",
    "editor_software_exif": "Признаки редактирования (EXIF)",
    "ela_high_variance": "Признаки редактирования (ELA)",
}

ACTION_LABELS: dict[ModerationAction, str] = {
    ModerationAction.APPROVE: "Одобрено",
    ModerationAction.REJECT: "Отклонено",
    ModerationAction.REQUEST_REUPLOAD_PHOTO: "Запрошено фото заново",
    ModerationAction.REQUEST_REUPLOAD_VIDEO: "Запрошено видео заново",
}


def flag_label(flag: str) -> str:
    return FLAG_LABELS.get(flag, flag)


def status_css_class(status: ApplicationStatus) -> str:
    return STATUS_CSS_CLASS.get(status, "neutral")


def format_dt(value: dt.datetime) -> str:
    return value.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m.%Y %H:%M")


def parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def parse_status(raw: str | None) -> ApplicationStatus | None:
    if not raw:
        return None
    try:
        return ApplicationStatus(raw)
    except ValueError:
        return None
