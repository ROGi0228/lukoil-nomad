import datetime as dt
import re

_LICENSE_NUMBER_RE = re.compile(r"^[A-Z]{2}\s?\d{6}$")
_IIN_RE = re.compile(r"^\d{12}$")

# Серия номера ВУ визуально совпадает в кириллице и латинице (АВСЕНКМОРТХУ похожи
# на ABCEHKMOPTXY) — OCR иногда отдаёт кириллические омоглифы вместо латиницы,
# хотя формат номера требует латиницу. parser.py уже нормализует на своей стороне,
# но проверка формата не должна полагаться на то, что вызывающий код это сделал.
_CYRILLIC_TO_LATIN_HOMOGLYPHS = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "С": "C",
        "Е": "E",
        "Н": "H",
        "К": "K",
        "М": "M",
        "О": "O",
        "Р": "P",
        "Т": "T",
        "Х": "X",
        "У": "Y",
    }
)
_DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")

# 7-й разряд ИИН РК кодирует век+пол рождения — используем только век,
# чтобы перепроверить дату рождения без риска ошибиться в контрольной сумме
# (сама контрольная сумма ИИН намеренно не реализована, см. модуль ниже).
_IIN_CENTURY_BY_DIGIT = {
    "1": 1800,
    "2": 1800,
    "3": 1900,
    "4": 1900,
    "5": 2000,
    "6": 2000,
}


def validate_license_number(raw: str) -> str | None:
    cleaned = raw.strip().upper().translate(_CYRILLIC_TO_LATIN_HOMOGLYPHS)
    if not _LICENSE_NUMBER_RE.match(cleaned):
        return None
    return cleaned


def validate_iin_format(raw: str) -> str | None:
    """Проверяет только формат (12 цифр), без контрольной суммы.

    Алгоритм контрольной суммы ИИН РК не реализован намеренно: без набора
    проверенных тестовых ИИН (валидных и невалидных) есть риск запрограммировать
    его неверно и начать отклонять настоящие документы (ложный отказ хуже,
    чем отсутствие проверки). При необходимости — реализовать и обязательно
    свериться на реальных образцах, прежде чем включать в авто-отказ.
    """
    cleaned = raw.strip()
    if not _IIN_RE.match(cleaned):
        return None
    return cleaned


def parse_document_date(raw: str) -> dt.date | None:
    match = _DATE_RE.match(raw.strip())
    if match is None:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def birth_date_from_iin(iin: str) -> dt.date | None:
    """Извлекает дату рождения из ИИН — полезная бесплатная сверка с полем 3 бланка."""
    if not _IIN_RE.match(iin):
        return None
    base_year = _IIN_CENTURY_BY_DIGIT.get(iin[6])
    if base_year is None:
        return None
    year = base_year + int(iin[0:2])
    month = int(iin[2:4])
    day = int(iin[4:6])
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def is_expired(expiry_date: dt.date, *, today: dt.date | None = None) -> bool:
    return expiry_date < (today or dt.date.today())
