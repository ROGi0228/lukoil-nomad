import pytest
from src.bot.utils.validators import normalize_phone, validate_city, validate_full_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Иванов Иван Иванович", "Иванов Иван Иванович"),
        ("  Иванов   Иван  ", "Иванов Иван"),
        ("Smith John", "Smith John"),
        ("Мынбаев Ерлік Бауыржанұлы", "Мынбаев Ерлік Бауыржанұлы"),
    ],
)
def test_validate_full_name_valid(raw: str, expected: str) -> None:
    assert validate_full_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "Иванов1", "A", "123 456", "Иванов"])
def test_validate_full_name_invalid(raw: str) -> None:
    assert validate_full_name(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+77071234567", "+77071234567"),
        ("87071234567", "+77071234567"),
        ("+7 707 123 45 67", "+77071234567"),
        ("7 (707) 123-45-67", "+77071234567"),
    ],
)
def test_normalize_phone_valid(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "123", "+7123"])
def test_normalize_phone_invalid(raw: str) -> None:
    assert normalize_phone(raw) is None


def test_validate_city_valid() -> None:
    assert validate_city("  Алматы ") == "Алматы"


@pytest.mark.parametrize("raw", ["", "A", "12345"])
def test_validate_city_invalid(raw: str) -> None:
    assert validate_city(raw) is None
