MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 120
# 20 МБ — предел скачивания файла через обычный (облачный) Telegram Bot API
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


def validate_video_metadata(duration: int | None, file_size: int | None) -> str | None:
    """Возвращает None, если видео проходит проверку, иначе — причину отказа.

    duration отсутствует, если видео прислано как Document (Telegram не даёт
    длительность для generic-файлов) — в этом случае проверяется только размер.
    """
    if duration is not None:
        if duration < MIN_DURATION_SECONDS:
            return f"Видео слишком короткое — минимум {MIN_DURATION_SECONDS} секунд."
        if duration > MAX_DURATION_SECONDS:
            return f"Видео слишком длинное — максимум {MAX_DURATION_SECONDS} секунд."

    if file_size is not None and file_size > MAX_FILE_SIZE_BYTES:
        max_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        return f"Файл слишком большой — максимум {max_mb} МБ."

    return None
