import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette import status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import format_dt
from src.db.models.admin_user import AdminUser
from src.db.repositories.task_repository import (
    create_task,
    get_task,
    list_dispatches_for_task,
    list_tasks,
)
from src.db.repositories.team_repository import get_team_score, list_teams
from src.db.session import async_session_factory

router = APIRouter(prefix="/tasks")
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt

_ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _to_utc(date_str: str, time_str: str) -> dt.datetime:
    naive = dt.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=_ALMATY_TZ).astimezone(dt.UTC)


@router.get("", response_class=HTMLResponse)
async def tasks_page(request: Request, admin: AdminUser = Depends(get_current_admin)) -> HTMLResponse:
    async with async_session_factory() as session:
        task_list = await list_tasks(session)
        teams = await list_teams(session)
        scores = {team.id: await get_team_score(session, team.id) for team in teams}

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
        },
    )


@router.post("", response_model=None)
async def create_task_route(
    title: str = Form(...),
    description: str = Form(...),
    send_date: str = Form(...),
    send_time: str = Form(...),
    is_daily: bool = Form(default=False),
    deadline_date: str = Form(default=""),
    deadline_time: str = Form(default=""),
    penalty_points: int = Form(default=2),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    send_at = _to_utc(send_date, send_time)

    if is_daily:
        deadline_at = _to_utc(send_date, "23:59")
    else:
        deadline_at = _to_utc(deadline_date or send_date, deadline_time or "23:59")

    async with async_session_factory() as session:
        await create_task(
            session,
            title=title,
            description=description,
            send_at=send_at,
            deadline_at=deadline_at,
            is_daily=is_daily,
            penalty_points=penalty_points,
        )
        await session.commit()

    return RedirectResponse("/tasks", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{task_id}", response_class=HTMLResponse)
async def task_detail(
    task_id: int, request: Request, admin: AdminUser = Depends(get_current_admin)
) -> HTMLResponse:
    async with async_session_factory() as session:
        task = await get_task(session, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        dispatches = await list_dispatches_for_task(session, task_id)

    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "task": task,
            "dispatches": dispatches,
        },
    )
