from aiogram import Bot
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette import status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import format_dt
from src.admin_panel.notify_helpers import notify_new_team_members
from src.bot.notify import notify_user
from src.core.config import get_settings
from src.db.models.admin_user import AdminUser
from src.db.models.task_dispatch import TaskDispatch
from src.db.repositories.application_repository import (
    get_application,
    get_application_contact,
    list_unassigned_applications,
)
from src.db.repositories.task_repository import (
    list_dispatches_for_application,
    list_dispatches_for_team,
)
from src.db.repositories.team_repository import (
    add_point_adjustment,
    create_team,
    get_team,
    get_team_score,
    list_point_adjustments,
    list_team_member_contacts,
    list_teams,
)
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage

router = APIRouter(prefix="/teams")
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt


@router.get("", response_class=HTMLResponse)
async def teams_page(request: Request, admin: AdminUser = Depends(get_current_admin)) -> HTMLResponse:
    async with async_session_factory() as session:
        teams = await list_teams(session)
        scores = {team.id: await get_team_score(session, team.id) for team in teams}
        unassigned = await list_unassigned_applications(session)

    return templates.TemplateResponse(
        request,
        "teams.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "teams": teams,
            "scores": scores,
            "unassigned": unassigned,
        },
    )


@router.post("", response_model=None)
async def create_team_route(
    request: Request,
    name: str = Form(...),
    member_ids: list[int] = Form(default=[]),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    assigned_ids: list[int] = []
    async with async_session_factory() as session:
        team = await create_team(session, name)
        team_id = team.id
        for application_id in member_ids:
            application = await get_application(session, application_id)
            if application is not None and application.team_id is None:
                application.team_id = team_id
                assigned_ids.append(application_id)
        await session.commit()

    if assigned_ids:
        bot: Bot = request.app.state.bot
        async with async_session_factory() as session:
            await notify_new_team_members(bot, session, team_id, assigned_ids)

    return RedirectResponse("/teams", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{team_id}", response_class=HTMLResponse)
async def team_detail(
    team_id: int, request: Request, admin: AdminUser = Depends(get_current_admin)
) -> HTMLResponse:
    async with async_session_factory() as session:
        team = await get_team(session, team_id)
        if team is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        score = await get_team_score(session, team_id)
        unassigned = await list_unassigned_applications(session)
        adjustments = await list_point_adjustments(session, team_id)
        team_dispatches = await list_dispatches_for_team(session, team_id)

        # Личные задания участников (Task.is_personal) тоже идут в счёт команды
        # (см. get_team_score), поэтому показываем их здесь же — иначе "баллы за
        # задания" на этой странице не сходились бы с общим счётом наверху.
        rows: list[tuple[TaskDispatch, str | None]] = [(d, None) for d in team_dispatches]
        for member in team.members:
            personal_dispatches = await list_dispatches_for_application(session, member.id)
            rows.extend((d, member.full_name) for d in personal_dispatches)
        rows.sort(key=lambda row: row[0].sent_at, reverse=True)

    storage = S3Storage(get_settings())
    submission_urls: dict[int, str] = {}
    for dispatch, _owner in rows:
        for item in dispatch.submission_items:
            if item.photo_key:
                submission_urls[item.id] = await storage.presigned_url(item.photo_key)
            elif item.video_key:
                submission_urls[item.id] = await storage.presigned_url(item.video_key)

    tasks_points_total = sum(d.points_awarded or 0 for d, _owner in rows)

    return templates.TemplateResponse(
        request,
        "team_detail.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "team": team,
            "score": score,
            "unassigned": unassigned,
            "adjustments": adjustments,
            "rows": rows,
            "submission_urls": submission_urls,
            "tasks_points_total": tasks_points_total,
        },
    )


@router.post("/{team_id}/adjust-points", response_model=None)
async def adjust_points_route(
    team_id: int,
    request: Request,
    points: int = Form(...),
    reason: str = Form(...),
    notify_scope: str = Form(default="team"),
    participant_id: str = Form(default=""),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    """Ручная корректировка баллов — снять ошибочный штраф, начислить бонус и т.п.,
    независимо от конкретного задания. Баллы всегда идут на счёт команды — выбор
    получателя уведомления (вся команда или один участник) на это не влияет."""
    async with async_session_factory() as session:
        await add_point_adjustment(
            session, team_id=team_id, points=points, reason=reason, admin_user_id=admin.id
        )
        await session.commit()

        if notify_scope == "participant" and participant_id:
            contact = await get_application_contact(session, int(participant_id))
            contacts = [contact] if contact else []
        else:
            contacts = await list_team_member_contacts(session, team_id)

    # Причина уходит как есть, без добавленного координатором текста вроде
    # "Вашей команде начислены баллы: +N." — само число баллов, если нужно,
    # координатор пишет в тексте причины (см. плейсхолдер поля выше).
    bot: Bot = request.app.state.bot
    for telegram_id, _language in contacts:
        await notify_user(bot, telegram_id, reason)

    return RedirectResponse(f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{team_id}/add-member", response_model=None)
async def add_team_member(
    team_id: int,
    request: Request,
    application_id: int = Form(...),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    assigned = False
    async with async_session_factory() as session:
        application = await get_application(session, application_id)
        if application is not None and application.team_id is None:
            application.team_id = team_id
            assigned = True
        await session.commit()

    if assigned:
        bot: Bot = request.app.state.bot
        async with async_session_factory() as session:
            await notify_new_team_members(bot, session, team_id, [application_id])

    return RedirectResponse(f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{team_id}/remove-member", response_model=None)
async def remove_team_member(
    team_id: int,
    application_id: int = Form(...),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    async with async_session_factory() as session:
        application = await get_application(session, application_id)
        if application is not None and application.team_id == team_id:
            application.team_id = None
        await session.commit()

    return RedirectResponse(f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)
