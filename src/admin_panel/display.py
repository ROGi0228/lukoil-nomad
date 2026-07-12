import datetime as dt

from src.shared.enums import ApplicationStatus

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
