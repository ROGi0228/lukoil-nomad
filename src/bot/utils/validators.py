import re

_PHONE_RE = re.compile(r"^\+\d{10,15}$")
_NAME_CHARS_RE = re.compile(r"^[А-Яа-яЁёA-Za-z\-\s]+$")


def validate_full_name(raw: str) -> str | None:
    cleaned = " ".join(raw.strip().split())
    if not (5 <= len(cleaned) <= 150) or not _NAME_CHARS_RE.match(cleaned):
        return None
    if len(cleaned.split()) < 2:
        return None
    return cleaned


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"[^\d+]", "", raw.strip())
    if digits.startswith("8") and len(digits) == 11:
        digits = "+7" + digits[1:]
    elif not digits.startswith("+"):
        digits = "+" + digits
    if not _PHONE_RE.match(digits):
        return None
    return digits


def validate_city(raw: str) -> str | None:
    cleaned = " ".join(raw.strip().split())
    if not (2 <= len(cleaned) <= 100) or not _NAME_CHARS_RE.match(cleaned):
        return None
    return cleaned
