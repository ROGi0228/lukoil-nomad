from src.services.ocr.parser import parse_driver_license

# Смоделированный текст на основе реального образца ВУ РК, присланного заказчиком
# (см. PROJECT_PLAN.md, Фаза 3) — имитирует то, что вернул бы document_text_detection.
SAMPLE_OCR_TEXT = """
ҚАЗАҚСТАН РЕСПУБЛИКАСЫ
РЕСПУБЛИКА КАЗАХСТАН
REPUBLIC OF KAZAKHSTAN
ЖҮРГІЗУШІ КУӘЛІГІ
ВОДИТЕЛЬСКОЕ УДОСТОВЕРЕНИЕ
DRIVING LICENCE
KZ
1. ЛЕЛЁТКА/ LELETKA
2. ИВАН ВЛАДИМИРОВИЧ/ IVAN
3. 03.10.1986, г. Алматы
4a) 12.02.2024 4b) 11.04.2027
4c) ДП г. Алматы
4d) ЖСН/IIN 861003399096
5. AF 977776
7.
9. B C B1 C1
12.
"""


def test_parse_driver_license_full_sample() -> None:
    result = parse_driver_license(SAMPLE_OCR_TEXT)

    assert result.surname == "ЛЕЛЁТКА"
    assert result.given_names == "ИВАН ВЛАДИМИРОВИЧ"
    assert result.birth_date == "03.10.1986"
    assert result.birth_place == "г. Алматы"
    assert result.issue_date == "12.02.2024"
    assert result.expiry_date == "11.04.2027"
    assert result.issuing_authority == "ДП г. Алматы"
    assert result.iin == "861003399096"
    assert result.license_number == "AF 977776"
    assert result.full_name == "ЛЕЛЁТКА ИВАН ВЛАДИМИРОВИЧ"


def test_parse_driver_license_empty_text_returns_all_none() -> None:
    result = parse_driver_license("")

    assert result.surname is None
    assert result.given_names is None
    assert result.birth_date is None
    assert result.license_number is None
    assert result.iin is None
    assert result.full_name == ""


def test_parse_driver_license_garbled_text_does_not_crash() -> None:
    result = parse_driver_license("случайный нераспознанный текст без полей")

    assert result.license_number is None
    assert result.iin is None
