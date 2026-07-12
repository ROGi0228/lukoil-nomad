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
