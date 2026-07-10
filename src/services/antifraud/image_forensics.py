import io

from PIL import ExifTags, Image, ImageChops

_EDITOR_SOFTWARE_KEYWORDS = ("photoshop", "gimp", "paint.net", "snapseed", "picsart", "lightroom")
_ELA_SUSPICIOUS_THRESHOLD = 80.0  # 0-255; см. оговорку в docstring analyze_image


def _ela_max_diff(image_bytes: bytes, quality: int = 90) -> float:
    original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buffer = io.BytesIO()
    original.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    resaved = Image.open(buffer)

    diff = ImageChops.difference(original, resaved)
    extrema = diff.getextrema()  # type: ignore[no-untyped-call]
    return float(max(channel_max for _, channel_max in extrema))


def _has_editor_software_exif(image_bytes: bytes) -> bool:
    image = Image.open(io.BytesIO(image_bytes))
    exif = image.getexif()
    if not exif:
        return False
    software_tag_id = next(
        (tag_id for tag_id, name in ExifTags.TAGS.items() if name == "Software"), None
    )
    if software_tag_id is None:
        return False
    software = str(exif.get(software_tag_id, "")).lower()
    return any(keyword in software for keyword in _EDITOR_SOFTWARE_KEYWORDS)


def analyze_image(image_bytes: bytes) -> list[str]:
    """Дешёвые эвристики признаков редактирования — не доказательство подделки,
    а вспомогательный флаг для модератора (см. раздел 8 PROJECT_PLAN.md, бюджетная
    связка вместо специализированного SDK проверки подлинности).

    Оговорки:
    - Telegram пересжимает и почти всегда стирает EXIF у фото, отправленных как "Photo"
      (сжатое изображение) — проверка EXIF реально работает только если пользователь
      прислал фото файлом ("Document"), поэтому она даёт скорее бонусный, чем гарантированный
      сигнал в текущем UX.
    - Порог ELA не откалиброван на реальных случаях подделки/не-подделки (таких образцов
      пока нет) — значение подобрано ориентировочно и должно быть пересмотрено, когда
      накопится статистика по реальным заявкам после запуска.
    """
    flags: list[str] = []

    if _has_editor_software_exif(image_bytes):
        flags.append("editor_software_exif")

    if _ela_max_diff(image_bytes) >= _ELA_SUSPICIOUS_THRESHOLD:
        flags.append("ela_high_variance")

    return flags
