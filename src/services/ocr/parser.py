import re
from dataclasses import dataclass

# Поля пронумерованы по международному образцу ВУ (Венская конвенция), которому
# следует бланк РК: 1 — фамилия, 2 — имя/отчество, 3 — дата и место рождения,
# 4a/4b — даты выдачи/окончания, 4c — орган выдачи, 4d — ЖСН/IIN, 5 — номер ВУ.
_SURNAME_RE = re.compile(r"1\.\s*([^\n/]+?)\s*/", re.UNICODE)
_GIVEN_NAMES_RE = re.compile(r"2\.\s*([^\n/]+?)\s*/", re.UNICODE)
_BIRTH_RE = re.compile(r"3\.\s*(\d{2}\.\d{2}\.\d{4}),?\s*(.+?)(?=\n|4a\)|$)", re.UNICODE)
_ISSUE_DATE_RE = re.compile(r"4a\)\s*(\d{2}\.\d{2}\.\d{4})")
_EXPIRY_DATE_RE = re.compile(r"4b\)\s*(\d{2}\.\d{2}\.\d{4})")
_AUTHORITY_RE = re.compile(r"4c\)\s*(.+?)(?=\n|4d\)|$)", re.UNICODE)
_IIN_RE = re.compile(r"(?:ЖСН|IIN)\D{0,10}(\d{12})", re.UNICODE)
_LICENSE_NUMBER_RE = re.compile(r"5\.\s*([A-Z]{2}\s?\d{6})")


@dataclass(frozen=True)
class ParsedDriverLicense:
    surname: str | None
    given_names: str | None
    birth_date: str | None
    birth_place: str | None
    issue_date: str | None
    expiry_date: str | None
    issuing_authority: str | None
    iin: str | None
    license_number: str | None

    @property
    def full_name(self) -> str:
        parts = [p for p in (self.surname, self.given_names) if p]
        return " ".join(parts)


def _match(pattern: re.Pattern[str], text: str, group: int = 1) -> str | None:
    m = pattern.search(text)
    return m.group(group).strip() if m else None


def parse_driver_license(raw_text: str) -> ParsedDriverLicense:
    birth_match = _BIRTH_RE.search(raw_text)

    return ParsedDriverLicense(
        surname=_match(_SURNAME_RE, raw_text),
        given_names=_match(_GIVEN_NAMES_RE, raw_text),
        birth_date=birth_match.group(1).strip() if birth_match else None,
        birth_place=birth_match.group(2).strip() if birth_match else None,
        issue_date=_match(_ISSUE_DATE_RE, raw_text),
        expiry_date=_match(_EXPIRY_DATE_RE, raw_text),
        issuing_authority=_match(_AUTHORITY_RE, raw_text),
        iin=_match(_IIN_RE, raw_text),
        license_number=_match(_LICENSE_NUMBER_RE, raw_text),
    )
