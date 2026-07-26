from aiogram import Bot
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette import status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import format_dt
from src.bot.i18n import resolve_lang, t
from src.bot.notify import notify_user
from src.db.models.admin_user import AdminUser
from src.db.repositories.application_repository import get_application
from src.db.repositories.team_repository import (
    add_point_adjustment,
    create_team,
    get_team,
    get_team_score,
    list_available_bloggers,
    list_available_winners,
    list_point_adjustments,
    list_team_member_contacts,
    list_teams,
)
from src.db.session import async_session_factory

router = APIRouter(prefix="/teams")
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt


@router.get("", response_class=HTMLResponse)
async def teams_page(request: Request, admin: AdminUser = Depends(get_current_admin)) -> HTMLResponse:
    async with async_session_factory() as session:
        teams = await list_teams(session)
        scores = {team.id: await get_team_score(session, team.id) for team in teams}
        winners = await list_available_winners(session)
        bloggers = await list_available_bloggers(session)

    return templates.TemplateResponse(
        request,
        "teams.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "teams": teams,
            "scores": scores,
            "winners": winners,
            "bloggers": bloggers,
        },
    )


@router.post("", response_model=None)
async def create_team_route(
    name: str = Form(...),
    member_ids: list[int] = Form(default=[]),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    async with async_session_factory() as session:
        team = await create_team(session, name)
        for application_id in member_ids:
            application = await get_application(session, application_id)
            if application is not None and application.team_id is None:
                application.team_id = team.id
        await session.commit()

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
        bloggers = await list_available_bloggers(session)
        winners = await list_available_winners(session)
        adjustments = await list_point_adjustments(session, team_id)

    return templates.TemplateResponse(
        request,
        "team_detail.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "team": team,
            "score": score,
            "bloggers": bloggers,
            "winners": winners,
            "adjustments": adjustments,
        },
    )


@router.post("/{team_id}/adjust-points", response_model=None)
async def adjust_points_route(
    team_id: int,
    request: Request,
    points: int = Form(...),
    reason: str = Form(...),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    """Ручная корректировка баллов — снять ошибочный штраф, начислить бонус и т.п.,
    независимо от конкретного задания. Уведомляет всех участников команды, как и
    остальные командные события (задания, штрафы, напоминания)."""
    async with async_session_factory() as session:
        await add_point_adjustment(
            session, team_id=team_id, points=points, reason=reason, admin_user_id=admin.id
        )
        await session.commit()
        contacts = await list_team_member_contacts(session, team_id)

    points_text = f"+{points}" if points > 0 else str(points)
    bot: Bot = request.app.state.bot
    for telegram_id, language in contacts:
        lang = resolve_lang(language)
        await notify_user(bot, telegram_id, t(lang, "team_points_adjusted", points=points_text, reason=reason))

    return RedirectResponse(f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{team_id}/add-member", response_model=None)
async def add_team_member(
    team_id: int,
    application_id: int = Form(...),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    async with async_session_factory() as session:
        application = await get_application(session, application_id)
        if application is not None and application.team_id is None:
            application.team_id = team_id
        await session.commit()

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
