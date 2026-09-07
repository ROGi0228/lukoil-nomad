import datetime as dt
from zoneinfo import ZoneInfo

# Клиент в Казахстане (UTC+5, без перехода на летнее время) — все временные метки
# в БД хранятся в UTC (timestamptz), в интерфейсе показываем сразу в местном времени.
DISPLAY_TIMEZONE = ZoneInfo("Asia/Almaty")


def format_dt(value: dt.datetime) -> str:
    return value.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m.%Y %H:%M")


def parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None
