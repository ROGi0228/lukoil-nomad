import datetime as dt

from src.admin_panel.display import parse_date


def test_parse_date_valid() -> None:
    assert parse_date("2026-07-12") == dt.date(2026, 7, 12)


def test_parse_date_none() -> None:
    assert parse_date(None) is None


def test_parse_date_empty_string() -> None:
    assert parse_date("") is None


def test_parse_date_invalid() -> None:
    assert parse_date("12.07.2026") is None
