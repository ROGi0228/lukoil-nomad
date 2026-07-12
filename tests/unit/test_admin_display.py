import datetime as dt

from src.admin_panel.display import parse_date, parse_status
from src.shared.enums import ApplicationStatus


def test_parse_date_valid() -> None:
    assert parse_date("2026-07-12") == dt.date(2026, 7, 12)


def test_parse_date_none() -> None:
    assert parse_date(None) is None


def test_parse_date_empty_string() -> None:
    assert parse_date("") is None


def test_parse_date_invalid() -> None:
    assert parse_date("12.07.2026") is None


def test_parse_status_valid() -> None:
    assert parse_status("pending_moderation") == ApplicationStatus.PENDING_MODERATION


def test_parse_status_none() -> None:
    assert parse_status(None) is None


def test_parse_status_invalid() -> None:
    assert parse_status("not_a_real_status") is None
