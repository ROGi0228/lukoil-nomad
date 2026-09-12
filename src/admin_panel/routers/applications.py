from aiogram import Bot
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import format_dt
from src.admin_panel.notify_helpers import notify_new_team_members
from src.bot.notify import notify_user
from src.db.models.admin_user import AdminUser
from src.db.models.application import Application
from src.db.models.user import User
from src.db.repositories.application_repository import get_application
from src.db.repositories.task_repository import delete_dispatches_for_application
from src.db.repositories.team_repository import list_teams
from src.db.session import async_session_factory

router = APIRouter(prefix="/applications")
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt


async def _load_application_and_user(
    session: AsyncSession, application_id: int
) -> tuple[Application, User]:
    application = await get_application(session, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    user = await session.get(User, application.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return application, user


@router.get("/{application_id}", response_class=HTMLResponse)
async def application_detail(
    application_id: int, request: Request, admin: AdminUser = Depends(get_current_admin)
) -> HTMLResponse:
    async with async_session_factory() as session:
        application = await get_application(session, application_id)
        if application is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        teams = await list_teams(session)

    return templates.TemplateResponse(
        request,
        "application_detail.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "application": application,
            "teams": teams,
        },
    )


@router.post("/{application_id}/assign-team", response_model=None)
async def assign_team(
    application_id: int,
    request: Request,
    team_id: str = Form(default=""),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    new_team_id = int(team_id) if team_id else None
    notify_team_id: int | None = None
    async with async_session_factory() as session:
        application = await get_application(session, application_id)
        if application is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if new_team_id is not None and application.team_id != new_team_id:
            notify_team_id = new_team_id
        application.team_id = new_team_id
        await session.commit()

    if notify_team_id is not None:
        bot: Bot = request.app.state.bot
        async with async_session_factory() as session:
            await notify_new_team_members(bot, session, notify_team_id, [application_id])

    return RedirectResponse(
        f"/applications/{application_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{application_id}/delete", response_model=None)
async def delete_application_route(
    application_id: int,
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    """Удаляет лишнюю/ошибочную регистрацию — например, участника, успевшего
    зарегистрироваться уже после того, как команды были сформированы. Заявку с
    командой тоже можно удалить (это не удаляет саму команду)."""
    async with async_session_factory() as session:
        application = await get_application(session, application_id)
        if application is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await delete_dispatches_for_application(session, application_id)
        await session.delete(application)
        await session.commit()

    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{application_id}/message", response_model=None)
async def message_applicant(
    application_id: int,
    request: Request,
    message: str = Form(...),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    async with async_session_factory() as session:
        _application, user = await _load_application_and_user(session, application_id)
        telegram_id = user.telegram_id

    bot: Bot = request.app.state.bot
    await notify_user(bot, telegram_id, message)

    return RedirectResponse(
        f"/applications/{application_id}", status_code=status.HTTP_303_SEE_OTHER
    )
