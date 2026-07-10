import io

from PIL import Image
from src.services.antifraud.image_forensics import analyze_image


def _make_jpeg_bytes(
    color: tuple[int, int, int] = (120, 140, 160), size: tuple[int, int] = (200, 200)
) -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def test_analyze_image_plain_photo_no_flags() -> None:
    flags = analyze_image(_make_jpeg_bytes())
    assert flags == []


def test_analyze_image_flags_editor_software_exif() -> None:
    image = Image.new("RGB", (200, 200), color=(120, 140, 160))
    exif = image.getexif()
    exif[0x0131] = "Adobe Photoshop 25.0"  # 0x0131 = стандартный EXIF-тег Software
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90, exif=exif)

    flags = analyze_image(buffer.getvalue())
    assert "editor_software_exif" in flags
