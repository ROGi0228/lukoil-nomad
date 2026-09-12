from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin
from src.shared.enums import TaskCriterion

# «Не выполнил» по новому ТЗ (Фаза 15) значит просто 0 баллов, не штраф — дефолт
# оставлен настраиваемым (не убран совсем), чтобы админ мог включить штраф точечно.
DEFAULT_PENALTY_POINTS = 0
DEFAULT_PASS_POINTS = 5
DEFAULT_RANK_POINTS = [30, 20, 10]


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)

    # Для командных заданий, где у каждой команды свой вариант текста (например,
    # разная тема для одной и той же фотозадачи) — {team_id (str): текст}. Команда,
    # для которой ключа нет, получает обычный description. NULL/{} — вариантов нет,
    # всем один текст (обычный случай). См. _send_dispatch в task_scheduler.py.
    team_text_overrides: Mapped[dict[str, str] | None] = mapped_column(JSONB)

    # Необязательный короткий код "день.задание" (например "1.1", "2.3") — если
    # задан, задание получает колонку в табличном /leaderboard: часть до первой
    # точки группирует задания по дню экспедиции, часть после — подпись колонки
    # для заданий текущего (последнего по номеру) дня; прошлые дни сворачиваются
    # в одну колонку с суммой баллов за день. NULL — задание (например, глобальная
    # миссия) не участвует в таблице по дням, только в общем счёте команды.
    short_code: Mapped[str | None] = mapped_column(String(20))

    # Личное задание (например, «зарегистрируйтесь в бонусном приложении» до того,
    # как участников распределили по командам) — рассылается каждому
    # зарегистрированному участнику отдельно (TaskDispatch.application_id), а не
    # командам (TaskDispatch.team_id). См. dispatch_to_participant в task_scheduler.py.
    is_personal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # когда воркер должен разослать задание всем командам разом. NULL — задание не на
    # фиксированное время, а по триггеру (см. trigger_task_id) — отправляется каждой
    # команде индивидуально, когда наступит её момент.
    send_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # если задано — это задание не рассылается по расписанию, а отправляется команде
    # через trigger_delay_minutes после того, как ЭТА ЖЕ команда выполнит trigger_task_id.
    # Раз на команду: идемпотентность обеспечивает уникальность (task_id, team_id) в
    # TaskDispatch — планировщик просто проверяет, есть ли уже диспетч, прежде чем создать.
    trigger_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    trigger_delay_minutes: Mapped[int | None] = mapped_column(Integer)

    # Критерий №1/2/3 из ТЗ заказчика (см. PROJECT_PLAN.md, Фаза 15) — определяет,
    # как считаются баллы за это задание. values_callable — та же причина, что и у
    # остальных enum-колонок в проекте: хранить .value ("pass_fail"), а не .name.
    criterion: Mapped[TaskCriterion] = mapped_column(
        SQLEnum(
            TaskCriterion,
            native_enum=False,
            validate_strings=True,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=TaskCriterion.PASS_FAIL,
        server_default=TaskCriterion.PASS_FAIL.value,
    )
    # criterion=PASS_FAIL — баллы за факт сдачи, вне зависимости от порядка
    pass_points: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_PASS_POINTS, server_default=str(DEFAULT_PASS_POINTS)
    )
    # criterion=SPEED_RANK — баллы за 1/2/3-е место по скорости сдачи (индекс списка
    # = место - 1), после списка — 0. criterion=MANUAL это поле не использует —
    # баллы там проставляет админ вручную на TaskDispatch.points_awarded.
    rank_points: Mapped[list[int]] = mapped_column(
        JSONB, default=list(DEFAULT_RANK_POINTS), server_default=text("'[30, 20, 10]'::jsonb")
    )

    # к какому моменту нужно уложиться — если не успели, штраф penalty_points.
    # Для "заданий дня" (is_daily=True) вычисляется как конец суток send_at админ-панелью
    # при создании, а не в рантайме. NULL — дедлайна нет вовсе, штраф никогда не начисляется
    # (list_dispatches_needing_penalty_check естественно отфильтровывает NULL в сравнении).
    deadline_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_daily: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    penalty_points: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_PENALTY_POINTS, server_default=str(DEFAULT_PENALTY_POINTS)
    )

    # воркер выставляет после реальной рассылки/после применения штрафов — идемпотентность
    # cron-джобов для заданий с фиксированным временем отправки (dispatched не используется
    # для заданий-триггеров — там идемпотентность на уровне TaskDispatch по команде)
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    penalties_applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Фото или видео, приложенное к заданию в админке — уходит вместе с текстом при
    # рассылке (bot.send_photo/send_video с текстом задания как caption вместо обычного
    # send_message). Взаимоисключающие: приложить можно либо фото, либо видео.
    attachment_photo_key: Mapped[str | None] = mapped_column(String(255))
    attachment_video_key: Mapped[str | None] = mapped_column(String(255))

    trigger_task: Mapped[Task | None] = relationship(remote_side=[id])
