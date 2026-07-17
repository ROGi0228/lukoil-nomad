from src.bot.i18n import Lang, t

MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 120
# 20 МБ — предел скачивания файла через обычный (облачный) Telegram Bot API
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


def validate_video_metadata(duration: int | None, file_size: int | None, lang: Lang) -> str | None:
    """Возвращает None, если видео проходит проверку, иначе — локализованную причину отказа.

    duration отсутствует, если видео прислано как Document (Telegram не даёт
    длительность для generic-файлов) — в этом случае проверяется только размер.
    """
    if duration is not None:
        if duration < MIN_DURATION_SECONDS:
            return t(lang, "video_too_short", min=MIN_DURATION_SECONDS)
        if duration > MAX_DURATION_SECONDS:
            return t(lang, "video_too_long", max=MAX_DURATION_SECONDS)

    if file_size is not None and file_size > MAX_FILE_SIZE_BYTES:
        max_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        return t(lang, "video_too_big", max_mb=max_mb)

    return None
