from src.db.repositories.task_repository import points_for_completion_rank


def test_first_place_gets_first_rank_points() -> None:
    assert points_for_completion_rank(0, [30, 20, 10]) == 30


def test_second_place_gets_second_rank_points() -> None:
    assert points_for_completion_rank(1, [30, 20, 10]) == 20


def test_third_place_gets_third_rank_points() -> None:
    assert points_for_completion_rank(2, [30, 20, 10]) == 10


def test_beyond_configured_ranks_gets_zero() -> None:
    assert points_for_completion_rank(3, [30, 20, 10]) == 0


def test_respects_custom_rank_points() -> None:
    assert points_for_completion_rank(0, [30, 30, 30]) == 30
    assert points_for_completion_rank(2, [30, 30, 30]) == 30
    assert points_for_completion_rank(3, [30, 30, 30]) == 0
