import re

# 20 МБ — предел скачивания файла через обычный (облачный) Telegram Bot API;
# используется при сдаче заданий вложением (src/bot/handlers/tasks.py)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

# Русская кириллица + латиница + казахские буквы, которых нет в стандартном русском
# алфавите (Әә Ғғ Ққ Ңң Өө Ұұ Үү Һһ Іі) — иначе казахские ФИО не проходят валидацию.
_NAME_CHARS_RE = re.compile(r"^[А-Яа-яЁёA-Za-zӘәҒғҚқҢңӨөҰұҮүҺһІі\-\s]+$")


def validate_full_name(raw: str) -> str | None:
    cleaned = " ".join(raw.strip().split())
    if not (5 <= len(cleaned) <= 150) or not _NAME_CHARS_RE.match(cleaned):
        return None
    if len(cleaned.split()) < 2:
        return None
    return cleaned
