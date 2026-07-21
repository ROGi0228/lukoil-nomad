from rapidfuzz import fuzz

DEFAULT_MATCH_THRESHOLD = 80.0

# OCR иногда путает визуально неотличимые кириллические и латинские буквы — на бланке
# КZ рядом с кириллицей идёт транслитерация ("1. СТАРОВ/ STAROV"), и движок иногда
# подхватывает латинский вариант вместо кириллического ("CTAPOB" вместо "СТАРОВ").
# Нормализуем обе стороны сравнения к кириллице, чтобы такие смешанные строки всё
# равно совпадали — иначе реальный документ владельца ложно отклоняется как чужой.
_LATIN_TO_CYRILLIC_HOMOGLYPHS = str.maketrans(
    {
        "A": "А",
        "B": "В",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "Р",
        "T": "Т",
        "X": "Х",
        "Y": "У",
    }
)


def _normalize_homoglyphs(value: str) -> str:
    return value.translate(_LATIN_TO_CYRILLIC_HOMOGLYPHS)


def fio_similarity(registered_full_name: str, document_full_name: str) -> float:
    registered = _normalize_homoglyphs(registered_full_name.upper())
    document = _normalize_homoglyphs(document_full_name.upper())
    # token_sort_ratio: устойчив к разному порядку слов (Фамилия/Имя/Отчество
    # на бланке идут раздельными полями, пользователь мог ввести в любом порядке)
    return fuzz.token_sort_ratio(registered, document)


def fio_matches(
    registered_full_name: str,
    document_full_name: str,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> bool:
    return fio_similarity(registered_full_name, document_full_name) >= threshold
