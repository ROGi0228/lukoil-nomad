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
