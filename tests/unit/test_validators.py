import pytest
from src.bot.utils.validators import validate_full_name


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
