from __future__ import annotations

from dataclasses import dataclass
from html import escape

from src.db.models.task_dispatch import TaskDispatch
from src.db.models.team import Team

# Имя команды в таблице обрезается до этой длины (с "…"), чтобы строка не расползалась
# на телефоне при большом числе колонок-дней к концу экспедиции.
TEAM_NAME_MAX_WIDTH = 14

# Экспедиция укладывается в один Telegram-текст с большим запасом даже в худшем
# случае (9 дней * ~4 задания + колонка "Итого" на ~25 команд) — порог на всякий
# случай, чтобы никогда не упереться в лимит Telegram на длину сообщения (4096).
MAX_CHARS_PER_MESSAGE = 3500

TASKS_LABEL = "Задания"


def _day_key(short_code: str) -> str:
    return short_code.split(".", 1)[0]


def _sort_key(value: str) -> str:
    """Числовые коды сортируются по значению (1, 2, ..., 10), а не лексикографически
    ("10" раньше "2") — нечисловые коды (админ ошибся форматом) уходят в конец."""
    try:
        return f"{int(value):010d}"
    except ValueError:
        return f"z{value}"


@dataclass(frozen=True)
class _Column:
    header: str
    is_today: bool
    key: str  # для колонки дня — сам day_key, для колонки задания — полный short_code


def _build_columns(short_codes: set[str]) -> list[_Column]:
    if not short_codes:
        return []
    day_keys = sorted({_day_key(code) for code in short_codes}, key=_sort_key)
    current_day = day_keys[-1]
    columns = [_Column(header=f"{day} день", is_today=False, key=day) for day in day_keys[:-1]]
    today_codes = sorted((c for c in short_codes if _day_key(c) == current_day), key=_sort_key)
    columns.extend(_Column(header=code, is_today=True, key=code) for code in today_codes)
    return columns


@dataclass(frozen=True)
class LeaderboardMatrix:
    """Сырые (ещё не выровненные пробелами) ячейки таблицы — команды отсортированы
    по убыванию "Итого". headers[0] и каждый rows[i][0] — колонка названия команды,
    последний элемент — колонка "Итого"; между ними — колонки дней/заданий."""

    headers: list[str]
    rows: list[list[str]]
    own_flags: list[bool]


def build_leaderboard_matrix(
    *,
    dispatches: list[TaskDispatch],
    teams: list[Team],
    scores: dict[int, int],
    own_team_id: int | None,
) -> LeaderboardMatrix:
    """Считает саму таблицу (какие колонки, какие значения), без выравнивания в
    текст. Колонка на каждое задание текущего (последнего по номеру дня среди
    short_code) дня + одна суммарная колонка на каждый прошедший день. "Итого" —
    авторитетный счёт команды (get_team_score, включая ручные корректировки), может
    не совпадать с суммой видимых колонок, если есть задания без short_code
    (например, глобальные миссии) — они учтены в общем счёте, но не в таблице."""
    short_codes = {d.task.short_code for d in dispatches if d.task.short_code}
    columns = _build_columns(short_codes)

    by_team: dict[int, dict[str, TaskDispatch]] = {}
    for d in dispatches:
        code = d.task.short_code
        if code:
            by_team.setdefault(d.team_id, {})[code] = d

    def cell_value(team_id: int, column: _Column) -> str:
        team_codes = by_team.get(team_id, {})
        if column.is_today:
            dispatch = team_codes.get(column.key)
            if dispatch is None or dispatch.points_awarded is None:
                return "-"
            return str(dispatch.points_awarded)
        total = sum(
            (d.points_awarded or 0) for code, d in team_codes.items() if _day_key(code) == column.key
        )
        return str(total)

    ranked = sorted(teams, key=lambda team: scores.get(team.id, 0), reverse=True)

    headers = ["Команда", *(c.header for c in columns), "Итого"]
    rows: list[list[str]] = []
    own_flags: list[bool] = []
    for team in ranked:
        name = (
            team.name
            if len(team.name) <= TEAM_NAME_MAX_WIDTH
            else team.name[: TEAM_NAME_MAX_WIDTH - 1] + "…"
        )
        rows.append([name, *(cell_value(team.id, c) for c in columns), str(scores.get(team.id, 0))])
        own_flags.append(team.id == own_team_id)

    return LeaderboardMatrix(headers=headers, rows=rows, own_flags=own_flags)


@dataclass(frozen=True)
class FormattedLeaderboard:
    """header_lines — строки, которые нужно повторять в начале каждого сообщения,
    если таблицу пришлось резать на несколько (chunk_leaderboard_messages):
    опциональная подпись "Задания" над колонками дней/заданий (её нет, если таких
    колонок нет вовсе) + строка с самими колонками. body_lines — по одной строке на
    команду."""

    header_lines: list[str]
    body_lines: list[str]


def format_leaderboard_matrix(matrix: LeaderboardMatrix) -> FormattedLeaderboard:
    """Выравнивает матрицу в моноширинный текст (имя команды — по левому краю,
    остальное — по правому) и HTML-экранирует — безопасно класть внутрь <pre> при
    parse_mode=HTML. Своя команда отмечена ведущей "*"."""
    if not matrix.rows:
        return FormattedLeaderboard(header_lines=[], body_lines=[])

    widths = [
        max(len(matrix.headers[i]), *(len(row[i]) for row in matrix.rows))
        for i in range(len(matrix.headers))
    ]

    def format_row(cells: list[str], marker: str) -> str:
        parts = [marker]
        for i, cell in enumerate(cells):
            parts.append(cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i]))
        return escape(" ".join(parts))

    header_lines: list[str] = []
    middle_widths = widths[1:-1]
    if middle_widths:
        # Подпись "Задания" центрируется ровно над колонками дней/заданий (между
        # "Команда" и "Итого") — ширина 1 (маркер) + 1 (пробел) + колонка "Команда" +
        # 1 (пробел) до начала этого блока совпадает с тем же префиксом в format_row.
        span_width = sum(middle_widths) + (len(middle_widths) - 1)
        prefix_width = 1 + 1 + widths[0] + 1
        label_line = " " * prefix_width + TASKS_LABEL.center(span_width)
        header_lines.append(escape(label_line.rstrip()))
    header_lines.append(format_row(matrix.headers, " "))

    body_lines = [
        format_row(cells, "*" if own else " ")
        for cells, own in zip(matrix.rows, matrix.own_flags, strict=True)
    ]
    return FormattedLeaderboard(header_lines=header_lines, body_lines=body_lines)


def build_leaderboard_rows(
    *,
    dispatches: list[TaskDispatch],
    teams: list[Team],
    scores: dict[int, int],
    own_team_id: int | None,
) -> FormattedLeaderboard:
    if not teams:
        return FormattedLeaderboard(header_lines=[], body_lines=[])
    matrix = build_leaderboard_matrix(
        dispatches=dispatches, teams=teams, scores=scores, own_team_id=own_team_id
    )
    return format_leaderboard_matrix(matrix)


def chunk_leaderboard_messages(formatted: FormattedLeaderboard) -> list[str]:
    """Режет готовые строки таблицы на отдельные сообщения (весь header_lines
    повторяется в каждом), так, чтобы ни одно не превысило лимит Telegram — на
    реальном масштабе (~20-25 команд) практически всегда укладывается в одно
    сообщение."""
    if not formatted.body_lines and not formatted.header_lines:
        return []

    header_block = "\n".join(formatted.header_lines)
    chunks: list[str] = []
    current: list[str] = [header_block] if formatted.header_lines else []
    current_len = len(header_block)
    min_lines = len(current)
    for line in formatted.body_lines:
        if current_len + len(line) + 1 > MAX_CHARS_PER_MESSAGE and len(current) > min_lines:
            chunks.append("\n".join(current))
            current = [header_block] if formatted.header_lines else []
            current_len = len(header_block)
        current.append(line)
        current_len += len(line) + 1
    chunks.append("\n".join(current))
    return chunks
