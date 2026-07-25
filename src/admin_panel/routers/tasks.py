import datetime as dt
from zoneinfo import ZoneInfo

from aiogram import Bot
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette import status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import format_dt
from src.bot.notify import try_delete_message
from src.core.config import get_settings
from src.db.models.admin_user import AdminUser
from src.db.repositories.task_repository import (
    create_task,
    get_task,
    list_dispatch_messages_for_task,
    list_dispatches_for_task,
    list_tasks,
    update_task,
)
from src.db.repositories.team_repository import get_team_score, list_teams
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage

router = APIRouter(prefix="/tasks")
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt

_ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _to_utc(date_str: str, time_str: str) -> dt.datetime:
    naive = dt.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=_ALMATY_TZ).astimezone(dt.UTC)


def _to_almaty_parts(value: dt.datetime | None) -> tuple[str, str]:
    """UTC datetime -> (YYYY-MM-DD, HH:MM) в Алматы, для предзаполнения <input date/time>."""
    if value is None:
        return "", ""
    local = value.astimezone(_ALMATY_TZ)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def _compute_schedule_and_deadline(
    *,
    schedule_mode: str,
    send_date: str,
    send_time: str,
    trigger_task_id: str,
    trigger_hours: int,
    trigger_minutes: int,
    is_daily: bool,
    no_deadline: bool,
    deadline_date: str,
    deadline_time: str,
) -> tuple[dt.datetime | None, int | None, int | None, dt.datetime | None]:
    """Возвращает (send_at, trigger_id, trigger_delay_minutes, deadline_at) — общая
    логика для создания и редактирования задания."""
    send_at: dt.datetime | None
    trigger_id: int | None
    delay_minutes: int | None

    if schedule_mode == "trigger":
        send_at = None
        trigger_id = int(trigger_task_id)
        delay_minutes = trigger_hours * 60 + trigger_minutes
    else:
        send_at = _to_utc(send_date, send_time)
        trigger_id = None
        delay_minutes = None

    deadline_at: dt.datetime | None
    if no_deadline:
        deadline_at = None
    elif is_daily and send_date:
        deadline_at = _to_utc(send_date, "23:59")
    elif deadline_date:
        deadline_at = _to_utc(deadline_date, deadline_time or "23:59")
    elif send_date:
        deadline_at = _to_utc(send_date, "23:59")
    else:
        deadline_at = None

    return send_at, trigger_id, delay_minutes, deadline_at


@router.get("", response_class=HTMLResponse)
async def tasks_page(request: Request, admin: AdminUser = Depends(get_current_admin)) -> HTMLResponse:
    async with async_session_factory() as session:
        task_list = await list_tasks(session)
        teams = await list_teams(session)
        scores = {team.id: await get_team_score(session, team.id) for team in teams}
        dispatch_counts = {
            task.id: len(await list_dispatches_for_task(session, task.id)) for task in task_list
        }

    leaderboard = sorted(teams, key=lambda team: scores[team.id], reverse=True)

    return templates.TemplateResponse(
        request,
        "tasks.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "tasks": task_list,
            "leaderboard": leaderboard,
            "scores": scores,
            "dispatch_counts": dispatch_counts,
            "total_teams": len(teams),
        },
    )


@router.post("", response_model=None)
async def create_task_route(
    title: str = Form(...),
    description: str = Form(...),
    schedule_mode: str = Form(default="fixed"),
    send_date: str = Form(default=""),
    send_time: str = Form(default=""),
    trigger_task_id: str = Form(default=""),
    trigger_hours: int = Form(default=0),
    trigger_minutes: int = Form(default=0),
    is_daily: bool = Form(default=False),
    no_deadline: bool = Form(default=False),
    deadline_date: str = Form(default=""),
    deadline_time: str = Form(default=""),
    penalty_points: int = Form(default=2),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    send_at, trigger_id, delay_minutes, deadline_at = _compute_schedule_and_deadline(
        schedule_mode=schedule_mode,
        send_date=send_date,
        send_time=send_time,
        trigger_task_id=trigger_task_id,
        trigger_hours=trigger_hours,
        trigger_minutes=trigger_minutes,
        is_daily=is_daily,
        no_deadline=no_deadline,
        deadline_date=deadline_date,
        deadline_time=deadline_time,
    )

    async with async_session_factory() as session:
        await create_task(
            session,
            title=title,
            description=description,
            send_at=send_at,
            deadline_at=deadline_at,
            is_daily=is_daily,
            penalty_points=penalty_points,
            trigger_task_id=trigger_id,
            trigger_delay_minutes=delay_minutes,
        )
        await session.commit()

    return RedirectResponse("/tasks", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{task_id}", response_class=HTMLResponse)
async def task_detail(
    task_id: int,
    request: Request,
    deleted: int | None = None,
    total: int | None = None,
    admin: AdminUser = Depends(get_current_admin),
) -> HTMLResponse:
    storage = S3Storage(get_settings())

    async with async_session_factory() as session:
        task = await get_task(session, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        dispatches = await list_dispatches_for_task(session, task_id)
        teams = await list_teams(session)
        message_count = len(await list_dispatch_messages_for_task(session, task_id))

    submission_urls: dict[int, str] = {}
    for dispatch in dispatches:
        for item in dispatch.submission_items:
            if item.photo_key:
                submission_urls[item.id] = await storage.presigned_url(item.photo_key)
            elif item.video_key:
                submission_urls[item.id] = await storage.presigned_url(item.video_key)

    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "task": task,
            "dispatches": dispatches,
            "total_teams": len(teams),
            "submission_urls": submission_urls,
            "message_count": message_count,
            "deleted": deleted,
            "total": total,
        },
    )


@router.post("/{task_id}/delete-messages", response_model=None)
async def delete_task_messages(
    task_id: int,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    """Отзывает у участников все сообщения о рассылке этого задания — на случай,
    если админ ошибся в данных задания и уже успел его разослать. Успешно удалённые
    записи убираются из БД (иначе кнопка/счётчик продолжали бы показывать их снова)."""
    bot: Bot = request.app.state.bot
    async with async_session_factory() as session:
        messages = await list_dispatch_messages_for_task(session, task_id)
        total_count = len(messages)
        deleted_count = 0
        for m in messages:
            if await try_delete_message(bot, m.telegram_id, m.message_id):
                await session.delete(m)
                deleted_count += 1
        await session.commit()

    return RedirectResponse(
        f"/tasks/{task_id}?deleted={deleted_count}&total={total_count}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{task_id}/edit", response_class=HTMLResponse)
async def edit_task_form(
    task_id: int, request: Request, admin: AdminUser = Depends(get_current_admin)
) -> HTMLResponse:
    async with async_session_factory() as session:
        task = await get_task(session, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        other_tasks = [t for t in await list_tasks(session) if t.id != task_id]

    send_date_value, send_time_value = _to_almaty_parts(task.send_at)
    deadline_date_value, deadline_time_value = _to_almaty_parts(task.deadline_at)

    return templates.TemplateResponse(
        request,
        "task_edit.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "task": task,
            "tasks": other_tasks,
            "send_date_value": send_date_value,
            "send_time_value": send_time_value or "09:00",
            "deadline_date_value": deadline_date_value,
            "deadline_time_value": deadline_time_value,
            "trigger_hours_value": (task.trigger_delay_minutes or 0) // 60,
            "trigger_minutes_value": (task.trigger_delay_minutes or 0) % 60,
        },
    )


@router.post("/{task_id}/edit", response_model=None)
async def edit_task_route(
    task_id: int,
    title: str = Form(...),
    description: str = Form(...),
    schedule_mode: str = Form(default="fixed"),
    send_date: str = Form(default=""),
    send_time: str = Form(default=""),
    trigger_task_id: str = Form(default=""),
    trigger_hours: int = Form(default=0),
    trigger_minutes: int = Form(default=0),
    is_daily: bool = Form(default=False),
    no_deadline: bool = Form(default=False),
    deadline_date: str = Form(default=""),
    deadline_time: str = Form(default=""),
    penalty_points: int = Form(default=2),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    send_at, trigger_id, delay_minutes, deadline_at = _compute_schedule_and_deadline(
        schedule_mode=schedule_mode,
        send_date=send_date,
        send_time=send_time,
        trigger_task_id=trigger_task_id,
        trigger_hours=trigger_hours,
        trigger_minutes=trigger_minutes,
        is_daily=is_daily,
        no_deadline=no_deadline,
        deadline_date=deadline_date,
        deadline_time=deadline_time,
    )

    async with async_session_factory() as session:
        task = await get_task(session, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await update_task(
            task,
            title=title,
            description=description,
            send_at=send_at,
            deadline_at=deadline_at,
            is_daily=is_daily,
            penalty_points=penalty_points,
            trigger_task_id=trigger_id,
            trigger_delay_minutes=delay_minutes,
        )
        await session.commit()

    return RedirectResponse(f"/tasks/{task_id}", status_code=status.HTTP_303_SEE_OTHER)
