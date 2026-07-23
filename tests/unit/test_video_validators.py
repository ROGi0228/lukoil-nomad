from src.bot.utils.video_validators import (
    MAX_DURATION_SECONDS,
    MAX_FILE_SIZE_BYTES,
    MIN_DURATION_SECONDS,
    validate_video_metadata,
)


def test_validate_video_metadata_ok() -> None:
    assert validate_video_metadata(30, 5 * 1024 * 1024, "ru") is None


def test_validate_video_metadata_too_short() -> None:
    error = validate_video_metadata(MIN_DURATION_SECONDS - 1, None, "ru")
    assert error is not None
    assert "критериям" in error


def test_validate_video_metadata_too_long() -> None:
    error = validate_video_metadata(MAX_DURATION_SECONDS + 1, None, "ru")
    assert error is not None
    assert "критериям" in error


def test_validate_video_metadata_too_large() -> None:
    error = validate_video_metadata(30, MAX_FILE_SIZE_BYTES + 1, "ru")
    assert error is not None
    assert "МБ" in error


def test_validate_video_metadata_no_duration_size_only() -> None:
    # Document без duration — проверяем только размер
    assert validate_video_metadata(None, 5 * 1024 * 1024, "ru") is None
    error = validate_video_metadata(None, MAX_FILE_SIZE_BYTES + 1, "ru")
    assert error is not None


def test_validate_video_metadata_boundary_values() -> None:
    assert validate_video_metadata(MIN_DURATION_SECONDS, None, "ru") is None
    assert validate_video_metadata(MAX_DURATION_SECONDS, None, "ru") is None
    assert validate_video_metadata(30, MAX_FILE_SIZE_BYTES, "ru") is None


def test_validate_video_metadata_kk_lang() -> None:
    error = validate_video_metadata(MIN_DURATION_SECONDS - 1, None, "kk")
    assert error is not None
    assert "талаптарға" in error
