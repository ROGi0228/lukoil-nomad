from src.bot.leaderboard_table import (
    FormattedLeaderboard,
    build_leaderboard_matrix,
    chunk_leaderboard_messages,
    format_leaderboard_matrix,
)
from src.db.models.task import Task
from src.db.models.task_dispatch import TaskDispatch
from src.db.models.team import Team


def _dispatch(team_id: int, short_code: str, points: int | None) -> TaskDispatch:
    return TaskDispatch(team_id=team_id, points_awarded=points, task=Task(short_code=short_code))


def test_single_day_matches_customer_mockup() -> None:
    """1.1 = 30, 1.2 = 0 (ещё единственный день — весь он "сегодня", колонок за
    прошлые дни нет)."""
    team = Team(id=1, name="Барсы")
    dispatches = [_dispatch(1, "1.1", 30), _dispatch(1, "1.2", 0)]

    matrix = build_leaderboard_matrix(dispatches=dispatches, teams=[team], scores={1: 30}, own_team_id=None)

    assert matrix.headers == ["Команда", "1.1", "1.2", "Итого"]
    assert matrix.rows == [["Барсы", "30", "0", "30"]]
    assert matrix.own_flags == [False]


def test_previous_day_collapses_into_one_column() -> None:
    """День 1 полностью в прошлом (30 баллов суммарно) — сворачивается в одну
    колонку "1 день"; день 2 — текущий, его задания идут отдельными колонками."""
    team = Team(id=1, name="Барсы")
    dispatches = [
        _dispatch(1, "1.1", 20),
        _dispatch(1, "1.2", 10),
        _dispatch(1, "2.1", 15),
        _dispatch(1, "2.2", 5),
    ]

    matrix = build_leaderboard_matrix(dispatches=dispatches, teams=[team], scores={1: 50}, own_team_id=None)

    assert matrix.headers == ["Команда", "1 день", "2.1", "2.2", "Итого"]
    assert matrix.rows == [["Барсы", "30", "15", "5", "50"]]


def test_numeric_day_sort_not_lexicographic() -> None:
    """День "10" не должен встать перед днём "2" (что случилось бы при обычной
    сортировке строк)."""
    team = Team(id=1, name="Барсы")
    dispatches = [_dispatch(1, "2.1", 1), _dispatch(1, "10.1", 2)]

    matrix = build_leaderboard_matrix(dispatches=dispatches, teams=[team], scores={1: 3}, own_team_id=None)

    # день 10 — самый поздний, значит "сегодня"; день 2 сворачивается в колонку
    assert matrix.headers == ["Команда", "2 день", "10.1", "Итого"]


def test_missing_dispatch_for_task_shown_as_dash() -> None:
    """Команда 2 не получала 1.2 вовсе (например, точечная wildcard-рассылка только
    команде 1) — прочерк, а не 0, чтобы не путать с реально нулевым результатом."""
    team1 = Team(id=1, name="Барсы")
    team2 = Team(id=2, name="Соколы")
    dispatches = [_dispatch(1, "1.1", 30), _dispatch(1, "1.2", 0), _dispatch(2, "1.1", 30)]

    matrix = build_leaderboard_matrix(
        dispatches=dispatches, teams=[team1, team2], scores={1: 30, 2: 30}, own_team_id=None
    )

    row_by_team = {row[0]: row for row in matrix.rows}
    assert row_by_team["Соколы"] == ["Соколы", "30", "-", "30"]


def test_unscored_manual_task_shown_as_dash_not_zero() -> None:
    team = Team(id=1, name="Барсы")
    dispatches = [_dispatch(1, "1.1", None)]

    matrix = build_leaderboard_matrix(dispatches=dispatches, teams=[team], scores={1: 0}, own_team_id=None)

    assert matrix.rows == [["Барсы", "-", "0"]]


def test_rows_sorted_by_score_descending() -> None:
    leader = Team(id=1, name="Лидеры")
    trailing = Team(id=2, name="Отстающие")
    dispatches = [_dispatch(1, "1.1", 30), _dispatch(2, "1.1", 5)]

    matrix = build_leaderboard_matrix(
        dispatches=dispatches, teams=[trailing, leader], scores={1: 30, 2: 5}, own_team_id=None
    )

    assert [row[0] for row in matrix.rows] == ["Лидеры", "Отстающие"]


def test_own_team_flagged() -> None:
    mine = Team(id=1, name="Барсы")
    other = Team(id=2, name="Соколы")
    matrix = build_leaderboard_matrix(dispatches=[], teams=[mine, other], scores={}, own_team_id=2)

    assert dict(zip((row[0] for row in matrix.rows), matrix.own_flags, strict=True)) == {
        "Барсы": False,
        "Соколы": True,
    }


def test_no_short_coded_tasks_falls_back_to_just_totals() -> None:
    team = Team(id=1, name="Барсы")
    matrix = build_leaderboard_matrix(dispatches=[], teams=[team], scores={1: 15}, own_team_id=None)

    assert matrix.headers == ["Команда", "Итого"]
    assert matrix.rows == [["Барсы", "15"]]


def test_long_team_name_truncated() -> None:
    team = Team(id=1, name="Очень Длинное Название Команды")
    matrix = build_leaderboard_matrix(dispatches=[], teams=[team], scores={1: 0}, own_team_id=None)

    assert matrix.rows[0][0] == "Очень Длинное…"
    assert len(matrix.rows[0][0]) == 14


def test_format_without_task_columns_has_no_tasks_label() -> None:
    """Нет заданий с short_code — колонок дней/заданий нет, подписывать нечего."""
    team = Team(id=1, name="АБ")
    matrix = build_leaderboard_matrix(dispatches=[], teams=[team], scores={1: 100}, own_team_id=1)

    formatted = format_leaderboard_matrix(matrix)

    assert len(formatted.header_lines) == 1
    header = formatted.header_lines[0]
    # Первая колонка (имя команды) — по левому краю, последняя (Итого) — по правому,
    # без хвостовых пробелов после числа.
    assert header.lstrip().startswith("Команда")
    assert header.endswith("Итого")
    assert formatted.body_lines[0].startswith("* АБ")
    assert formatted.body_lines[0].endswith("100")
    assert len(header) == len(formatted.body_lines[0])


def test_format_with_task_columns_adds_centered_tasks_label() -> None:
    team = Team(id=1, name="Барсы")
    dispatches = [_dispatch(1, "1.1", 30), _dispatch(1, "1.2", 0)]
    matrix = build_leaderboard_matrix(dispatches=dispatches, teams=[team], scores={1: 30}, own_team_id=None)

    formatted = format_leaderboard_matrix(matrix)

    assert len(formatted.header_lines) == 2
    label_line, columns_line = formatted.header_lines
    assert label_line.strip() == "Задания"
    # Подпись помещается точно над блоком колонок 1.1/1.2 в строке с кодами — не
    # заезжает ни на "Команда", ни на "Итого".
    label_start = label_line.index("Задания")
    label_end = label_start + len("Задания")
    columns_start = columns_line.index("1.1")
    columns_end = columns_line.index("Итого")
    assert columns_start <= label_start
    assert label_end <= columns_end
    assert len(label_line) <= len(columns_line)


def test_chunk_leaderboard_messages_repeats_full_header_when_split() -> None:
    formatted = FormattedLeaderboard(header_lines=["label", "header"], body_lines=["row1", "row2", "row3"])
    chunks = chunk_leaderboard_messages(formatted)
    assert chunks == ["label\nheader\nrow1\nrow2\nrow3"]

    # Принудительно маленький лимит — эмулируем большой рейтинг через саму функцию,
    # проверяя, что каждая часть начинается с ПОЛНОГО заголовка (обе строки).
    from src.bot import leaderboard_table

    original_limit = leaderboard_table.MAX_CHARS_PER_MESSAGE
    leaderboard_table.MAX_CHARS_PER_MESSAGE = len("label\nheader") + len("row1") + 2
    try:
        chunks = leaderboard_table.chunk_leaderboard_messages(formatted)
    finally:
        leaderboard_table.MAX_CHARS_PER_MESSAGE = original_limit

    assert len(chunks) > 1
    assert all(chunk.startswith("label\nheader") for chunk in chunks)


def test_chunk_leaderboard_messages_empty_input() -> None:
    assert chunk_leaderboard_messages(FormattedLeaderboard(header_lines=[], body_lines=[])) == []
