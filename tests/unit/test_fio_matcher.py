from src.services.verification.fio_matcher import fio_matches


def test_fio_matches_identical() -> None:
    assert fio_matches("Лелётка Иван Владимирович", "ЛЕЛЁТКА ИВАН ВЛАДИМИРОВИЧ") is True


def test_fio_matches_different_word_order() -> None:
    assert fio_matches("Иван Владимирович Лелётка", "ЛЕЛЁТКА ИВАН ВЛАДИМИРОВИЧ") is True


def test_fio_matches_minor_typo() -> None:
    assert fio_matches("Лелетка Иван Владимирович", "ЛЕЛЁТКА ИВАН ВЛАДИМИРОВИЧ") is True


def test_fio_matches_different_person() -> None:
    assert fio_matches("Иванов Иван Иванович", "ЛЕЛЁТКА ИВАН ВЛАДИМИРОВИЧ") is False


def test_fio_matches_ocr_latin_cyrillic_homoglyphs() -> None:
    # Реальный случай: OCR прочитал "СТАРОВ" латинскими буквами-омоглифами "CTAPOB"
    assert fio_matches("Старов Никита Иванович", "CTAPOB НИКИТА ИВАНОВИЧ") is True
