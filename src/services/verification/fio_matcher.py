from rapidfuzz import fuzz

DEFAULT_MATCH_THRESHOLD = 80.0


def fio_similarity(registered_full_name: str, document_full_name: str) -> float:
    # token_sort_ratio: устойчив к разному порядку слов (Фамилия/Имя/Отчество
    # на бланке идут раздельными полями, пользователь мог ввести в любом порядке)
    return fuzz.token_sort_ratio(registered_full_name.upper(), document_full_name.upper())


def fio_matches(
    registered_full_name: str,
    document_full_name: str,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> bool:
    return fio_similarity(registered_full_name, document_full_name) >= threshold
