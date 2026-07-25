from aiogram import Bot
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status as http_status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import format_dt
from src.bot.notify import notify_user, try_delete_message
from src.db.models.admin_user import AdminUser
from src.db.models.application import Application
from src.db.models.team import Team
from src.db.repositories.application_repository import (
    get_application_contact,
    list_winners_and_bloggers,
    list_winners_and_bloggers_contacts,
)
from src.db.repositories.broadcast_repository import (
    add_broadcast_message,
    create_broadcast,
    list_broadcast_messages,
    list_broadcasts,
)
from src.db.repositories.team_repository import list_team_member_contacts, list_teams
from src.db.session import async_session_factory

router = APIRouter(prefix="/broadcast")
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt


async def _resolve_contacts(
    session: AsyncSession, audience: str, team: str, participant: str
) -> list[tuple[int, str | None]]:
    if audience == "team":
        if not team:
            return []
        return await list_team_member_contacts(session, int(team))
    if audience == "participant":
        if not participant:
            return []
        contact = await get_application_contact(session, int(participant))
        return [contact] if contact else []
    return await list_winners_and_bloggers_contacts(session)


def _audience_label(
    audience: str, team: str, participant: str, teams: list[Team], participants: list[Application]
) -> str:
    if audience == "team":
        matched_team = next((t for t in teams if str(t.id) == team), None)
        return f"Команда «{matched_team.name}»" if matched_team else "Команда (не выбрана)"
    if audience == "participant":
        matched_app = next((a for a in participants if str(a.id) == participant), None)
        return f"Участник: {matched_app.full_name}" if matched_app else "Участник (не выбран)"
    return "Все победители и блогеры"


@router.get("", response_class=HTMLResponse)
async def broadcast_page(
    request: Request,
    sent: int | None = None,
    deleted: int | None = None,
    total: int | None = None,
    admin: AdminUser = Depends(get_current_admin),
) -> HTMLResponse:
    async with async_session_factory() as session:
        teams = await list_teams(session)
        participants = await list_winners_and_bloggers(session)
        history = await list_broadcasts(session)
        history_counts = {b.id: len(await list_broadcast_messages(session, b.id)) for b in history}

    return templates.TemplateResponse(
        request,
        "broadcast.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "teams": teams,
            "participants": participants,
            "recipient_count": None,
            "sent_count": sent,
            "deleted": deleted,
            "total": total,
            "history": history,
            "history_counts": history_counts,
            "form": {"audience": "all", "team": "", "participant": "", "message": ""},
        },
    )


@router.post("", response_model=None)
async def broadcast_submit(
    request: Request,
    action: str = Form(...),
    audience: str = Form("all"),
    team: str = Form(""),
    participant: str = Form(""),
    message: str = Form(""),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> HTMLResponse | RedirectResponse:
    async with async_session_factory() as session:
        contacts = await _resolve_contacts(session, audience, team, participant)
        teams = await list_teams(session)
        participants = await list_winners_and_bloggers(session)

    if action == "send" and message.strip():
        bot: Bot = request.app.state.bot
        label = _audience_label(audience, team, participant, teams, participants)
        async with async_session_factory() as session:
            broadcast = await create_broadcast(
                session, message=message, audience_label=label, admin_user_id=admin.id
            )
            await session.commit()
            for telegram_id, _language in contacts:
                sent_message = await notify_user(bot, telegram_id, message)
                if sent_message is not None:
                    await add_broadcast_message(
                        session,
                        broadcast_id=broadcast.id,
                        telegram_id=telegram_id,
                        message_id=sent_message.message_id,
                    )
            await session.commit()
        return RedirectResponse(
            f"/broadcast?sent={len(contacts)}", status_code=http_status.HTTP_303_SEE_OTHER
        )

    async with async_session_factory() as session:
        history = await list_broadcasts(session)
        history_counts = {b.id: len(await list_broadcast_messages(session, b.id)) for b in history}

    return templates.TemplateResponse(
        request,
        "broadcast.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "teams": teams,
            "participants": participants,
            "recipient_count": len(contacts),
            "sent_count": None,
            "deleted": None,
            "total": None,
            "history": history,
            "history_counts": history_counts,
            "form": {
                "audience": audience,
                "team": team,
                "participant": participant,
                "message": message,
            },
        },
    )


@router.post("/{broadcast_id}/delete", response_model=None)
async def delete_broadcast_messages(
    broadcast_id: int,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    bot: Bot = request.app.state.bot
    async with async_session_factory() as session:
        messages = await list_broadcast_messages(session, broadcast_id)
        total_count = len(messages)
        deleted_count = 0
        for m in messages:
            if await try_delete_message(bot, m.telegram_id, m.message_id):
                await session.delete(m)
                deleted_count += 1
        await session.commit()

    return RedirectResponse(
        f"/broadcast?deleted={deleted_count}&total={total_count}",
        status_code=http_status.HTTP_303_SEE_OTHER,
    )
