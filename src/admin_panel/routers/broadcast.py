from aiogram import Bot
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status as http_status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import STATUS_LABELS
from src.bot.notify import notify_user
from src.db.models.admin_user import AdminUser
from src.db.repositories.application_repository import list_application_contacts
from src.db.repositories.team_repository import list_teams
from src.db.repositories.user_repository import list_all_user_contacts
from src.db.session import async_session_factory
from src.shared.enums import ApplicationStatus

router = APIRouter(prefix="/broadcast")
templates = Jinja2Templates(directory="src/admin_panel/templates")


async def _resolve_contacts(
    session: AsyncSession, audience: str, status_filter: str, city: str, team: str
) -> list[tuple[int, str | None]]:
    if audience == "all":
        return await list_all_user_contacts(session)

    parsed_status = ApplicationStatus(status_filter) if status_filter else None
    team_id = int(team) if team and team != "none" else None
    no_team = team == "none"

    return await list_application_contacts(
        session,
        status=parsed_status,
        city=city or None,
        team_id=team_id,
        no_team=no_team,
    )


@router.get("", response_class=HTMLResponse)
async def broadcast_page(
    request: Request,
    sent: int | None = None,
    admin: AdminUser = Depends(get_current_admin),
) -> HTMLResponse:
    async with async_session_factory() as session:
        teams = await list_teams(session)

    return templates.TemplateResponse(
        request,
        "broadcast.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "status_labels": STATUS_LABELS,
            "teams": teams,
            "recipient_count": None,
            "sent_count": sent,
            "form": {"audience": "all", "status": "", "city": "", "team": "", "message": ""},
        },
    )


@router.post("", response_model=None)
async def broadcast_submit(
    request: Request,
    action: str = Form(...),
    audience: str = Form("all"),
    status: str = Form(""),
    city: str = Form(""),
    team: str = Form(""),
    message: str = Form(""),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> HTMLResponse | RedirectResponse:
    async with async_session_factory() as session:
        contacts = await _resolve_contacts(session, audience, status, city, team)
        teams = await list_teams(session)

    if action == "send" and message.strip():
        bot: Bot = request.app.state.bot
        for telegram_id, _language in contacts:
            await notify_user(bot, telegram_id, message)
        return RedirectResponse(
            f"/broadcast?sent={len(contacts)}", status_code=http_status.HTTP_303_SEE_OTHER
        )

    return templates.TemplateResponse(
        request,
        "broadcast.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "status_labels": STATUS_LABELS,
            "teams": teams,
            "recipient_count": len(contacts),
            "sent_count": None,
            "form": {
                "audience": audience,
                "status": status,
                "city": city,
                "team": team,
                "message": message,
            },
        },
    )
