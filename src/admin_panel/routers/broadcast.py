from aiogram import Bot
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status as http_status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.bot.notify import notify_user
from src.db.models.admin_user import AdminUser
from src.db.repositories.application_repository import list_winners_and_bloggers_contacts
from src.db.repositories.team_repository import list_team_member_contacts, list_teams
from src.db.session import async_session_factory

router = APIRouter(prefix="/broadcast")
templates = Jinja2Templates(directory="src/admin_panel/templates")


async def _resolve_contacts(
    session: AsyncSession, audience: str, team: str
) -> list[tuple[int, str | None]]:
    if audience == "team" and team:
        return await list_team_member_contacts(session, int(team))
    return await list_winners_and_bloggers_contacts(session)


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
            "teams": teams,
            "recipient_count": None,
            "sent_count": sent,
            "form": {"audience": "all", "team": "", "message": ""},
        },
    )


@router.post("", response_model=None)
async def broadcast_submit(
    request: Request,
    action: str = Form(...),
    audience: str = Form("all"),
    team: str = Form(""),
    message: str = Form(""),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> HTMLResponse | RedirectResponse:
    async with async_session_factory() as session:
        contacts = await _resolve_contacts(session, audience, team)
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
            "teams": teams,
            "recipient_count": len(contacts),
            "sent_count": None,
            "form": {"audience": audience, "team": team, "message": message},
        },
    )
