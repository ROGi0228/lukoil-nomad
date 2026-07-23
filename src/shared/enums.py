import enum


class ApplicationStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_DOCUMENT = "pending_document"
    PENDING_OCR = "pending_ocr"
    DOCUMENT_FLAGGED = "document_flagged"
    PENDING_VIDEO = "pending_video"
    PENDING_MODERATION = "pending_moderation"
    APPROVED = "approved"
    REJECTED = "rejected"


class ModerationAction(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REUPLOAD_PHOTO = "request_reupload_photo"
    REQUEST_REUPLOAD_VIDEO = "request_reupload_video"
    # Документ проверен модератором вручную (снят флаг DOCUMENT_FLAGGED) и участник
    # переведён к загрузке видео — в отличие от REQUEST_REUPLOAD_VIDEO, видео при
    # этом действии ещё ни разу не присылалось, это не повторный запрос.
    APPROVE_DOCUMENT = "approve_document"
    ADMIN_MESSAGE = "admin_message"


class SelectionStage(str, enum.Enum):
    """Стадия конкурсного отбора — независима от ApplicationStatus (тот про пайплайн
    регистрации/модерации документов, этот — про голосование за уже одобренных).
    NULL на Application означает "ещё не участвует ни в каком отборе" (только что одобрен)."""

    VOTING = "voting"
    ELIMINATED_STAGE1 = "eliminated_stage1"
    WINNER = "winner"
    ELIMINATED_STAGE2 = "eliminated_stage2"
