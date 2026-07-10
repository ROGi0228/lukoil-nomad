import datetime as dt

import pytest
from src.services.verification.document_validator import (
    birth_date_from_iin,
    is_expired,
    parse_document_date,
    validate_iin_format,
    validate_license_number,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AF 977776", "AF 977776"),
        ("af977776", "AF977776"),
        ("  AF 977776  ", "AF 977776"),
    ],
)
def test_validate_license_number_valid(raw: str, expected: str) -> None:
    assert validate_license_number(raw) == expected


@pytest.mark.parametrize("raw", ["", "A1 977776", "AF97776", "AF 9777760", "977776"])
def test_validate_license_number_invalid(raw: str) -> None:
    assert validate_license_number(raw) is None


def test_validate_iin_format_valid() -> None:
    assert validate_iin_format("861003399096") == "861003399096"


@pytest.mark.parametrize("raw", ["", "86100339909", "8610033990961", "86100339909a"])
def test_validate_iin_format_invalid(raw: str) -> None:
    assert validate_iin_format(raw) is None


def test_parse_document_date_valid() -> None:
    assert parse_document_date("12.02.2024") == dt.date(2024, 2, 12)


@pytest.mark.parametrize("raw", ["31.02.2024", "2024-02-12", "", "12/02/2024"])
def test_parse_document_date_invalid(raw: str) -> None:
    assert parse_document_date(raw) is None


def test_birth_date_from_iin_matches_real_sample() -> None:
    # ИИН с образца ВУ РК, присланного заказчиком: 861003399096 -> ДР 03.10.1986
    assert birth_date_from_iin("861003399096") == dt.date(1986, 10, 3)


def test_birth_date_from_iin_invalid_format_returns_none() -> None:
    assert birth_date_from_iin("123") is None


def test_is_expired_past_date() -> None:
    assert is_expired(dt.date(2020, 1, 1), today=dt.date(2026, 7, 10)) is True


def test_is_expired_future_date() -> None:
    assert is_expired(dt.date(2027, 4, 11), today=dt.date(2026, 7, 10)) is False
