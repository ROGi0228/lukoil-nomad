import datetime as dt
from zoneinfo import ZoneInfo

from aiogram import Bot
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette import status as http_status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import format_dt
from src.bot.notify import try_delete_message
from src.core.config import get_settings
from src.db.models.admin_user import AdminUser
from src.db.models.application import Application
from src.db.models.team import Team
from src.db.repositories.application_repository import list_all_applications
from src.db.repositories.broadcast_repository import (
    add_broadcast_message,
    create_broadcast,
    get_broadcast,
    list_broadcast_messages,
    list_broadcasts,
    resolve_broadcast_contacts,
    set_broadcast_attachment,
    update_broadcast,
)
from src.db.repositories.team_repository import list_teams
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage
from src.workers.tasks.broadcast_scheduler import send_broadcast_message

router = APIRouter(prefix="/broadcast")
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt

_ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _to_utc(date_str: str, time_str: str) -> dt.datetime:
    naive = dt.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=_ALMATY_TZ).astimezone(dt.UTC)


def _to_almaty_parts(value: dt.datetime) -> tuple[str, str]:
    local = value.astimezone(_ALMATY_TZ)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


async def _save_attachment(
    storage: S3Storage, broadcast_id: int, attachment: UploadFile | None
) -> tuple[str | None, str | None]:
    """Загружает вложение рассылки в S3, если оно есть, и возвращает (photo_key,
    video_key) — ровно одно из двух заполнено, по content_type файла. (None, None),
    если вложения нет вовсе (см. _save_attachment в routers/tasks.py — та же идея)."""
    if attachment is None or not attachment.filename:
        return None, None

    content_type = attachment.content_type or ""
    data = await attachment.read()
    if not data:
        return None, None

    if content_type.startswith("video/"):
        key = f"broadcast_attachments/{broadcast_id}/{attachment.filename}"
        await storage.upload(key, data, content_type=content_type)
        return None, key

    key = f"broadcast_attachments/{broadcast_id}/{attachment.filename}"
    await storage.upload(key, data, content_type=content_type or "image/jpeg")
    return key, None


def _audience_label(
    audience: str, team: str, participant: str, teams: list[Team], participants: list[Application]
) -> str:
    if audience == "team":
        matched_team = next((t for t in teams if str(t.id) == team), None)
        return f"Команда «{matched_team.name}»" if matched_team else "Команда (не выбрана)"
    if audience == "participant":
        matched_app = next((a for a in participants if str(a.id) == participant), None)
        return f"Участник: {matched_app.full_name}" if matched_app else "Участник (не выбран)"
    if audience == "teams":
        return "Все команды"
    return "Все зарегистрированные участники"


@router.get("", response_class=HTMLResponse)
async def broadcast_page(
    request: Request,
    sent: int | None = None,
    deleted: int | None = None,
    total: int | None = None,
    scheduled: int | None = None,
    cancelled: int | None = None,
    edited: int | None = None,
    admin: AdminUser = Depends(get_current_admin),
) -> HTMLResponse:
    async with async_session_factory() as session:
        teams = await list_teams(session)
        participants = await list_all_applications(session)
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
            "scheduled": scheduled,
            "cancelled": cancelled,
            "edited": edited,
            "history": history,
            "history_counts": history_counts,
            "form": {
                "audience": "all",
                "team": "",
                "participant": "",
                "message": "",
                "schedule_mode": "now",
                "send_date": "",
                "send_time": "",
            },
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
    schedule_mode: str = Form("now"),
    send_date: str = Form(""),
    send_time: str = Form(""),
    attachment: UploadFile | None = File(default=None),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> HTMLResponse | RedirectResponse:
    team_id = int(team) if team else None
    participant_id = int(participant) if participant else None

    async with async_session_factory() as session:
        contacts = await resolve_broadcast_contacts(
            session, audience=audience, team_id=team_id, participant_id=participant_id
        )
        teams = await list_teams(session)
        participants = await list_all_applications(session)

    if action == "send" and message.strip():
        label = _audience_label(audience, team, participant, teams, participants)
        storage = S3Storage(get_settings())

        if schedule_mode == "later" and send_date and send_time:
            send_at = _to_utc(send_date, send_time)
            async with async_session_factory() as session:
                broadcast = await create_broadcast(
                    session,
                    message=message,
                    audience_label=label,
                    admin_user_id=admin.id,
                    audience=audience,
                    team_id=team_id,
                    participant_id=participant_id,
                    send_at=send_at,
                    sent_at=None,
                )
                await session.flush()
                photo_key, video_key = await _save_attachment(storage, broadcast.id, attachment)
                if photo_key or video_key:
                    set_broadcast_attachment(broadcast, photo_key=photo_key, video_key=video_key)
                await session.commit()
            return RedirectResponse(
                "/broadcast?scheduled=1", status_code=http_status.HTTP_303_SEE_OTHER
            )

        bot: Bot = request.app.state.bot
        now = dt.datetime.now(dt.UTC)
        async with async_session_factory() as session:
            broadcast = await create_broadcast(
                session,
                message=message,
                audience_label=label,
                admin_user_id=admin.id,
                audience=audience,
                team_id=team_id,
                participant_id=participant_id,
                send_at=now,
                sent_at=now,
            )
            await session.flush()
            photo_key, video_key = await _save_attachment(storage, broadcast.id, attachment)
            if photo_key or video_key:
                set_broadcast_attachment(broadcast, photo_key=photo_key, video_key=video_key)
            await session.commit()
            for telegram_id, _language in contacts:
                sent_message = await send_broadcast_message(bot, storage, broadcast, telegram_id)
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
                "schedule_mode": schedule_mode,
                "send_date": send_date,
                "send_time": send_time,
            },
        },
    )


@router.post("/{broadcast_id}/cancel", response_model=None)
async def cancel_scheduled_broadcast(
    broadcast_id: int,
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    """Отменяет ещё не отправленную запланированную рассылку — удаляет её целиком,
    так как отправленных сообщений (BroadcastMessage) у неё ещё нет."""
    async with async_session_factory() as session:
        broadcast = await get_broadcast(session, broadcast_id)
        if broadcast is None:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND)
        if broadcast.sent_at is not None:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST)
        await session.delete(broadcast)
        await session.commit()

    return RedirectResponse("/broadcast?cancelled=1", status_code=http_status.HTTP_303_SEE_OTHER)


@router.get("/{broadcast_id}/edit", response_class=HTMLResponse)
async def edit_broadcast_form(
    broadcast_id: int, request: Request, admin: AdminUser = Depends(get_current_admin)
) -> HTMLResponse:
    async with async_session_factory() as session:
        broadcast = await get_broadcast(session, broadcast_id)
        if broadcast is None or broadcast.sent_at is not None:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND)
        teams = await list_teams(session)
        participants = await list_all_applications(session)

    send_date, send_time = _to_almaty_parts(broadcast.send_at)

    attachment_url = None
    storage = S3Storage(get_settings())
    if broadcast.attachment_photo_key:
        attachment_url = await storage.presigned_url(broadcast.attachment_photo_key)
    elif broadcast.attachment_video_key:
        attachment_url = await storage.presigned_url(broadcast.attachment_video_key)

    return templates.TemplateResponse(
        request,
        "broadcast_edit.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "broadcast": broadcast,
            "teams": teams,
            "participants": participants,
            "attachment_url": attachment_url,
            "form": {
                "audience": broadcast.audience,
                "team": str(broadcast.team_id) if broadcast.team_id else "",
                "participant": str(broadcast.participant_id) if broadcast.participant_id else "",
                "message": broadcast.message,
                "send_date": send_date,
                "send_time": send_time,
            },
        },
    )


@router.post("/{broadcast_id}/edit", response_model=None)
async def edit_broadcast_route(
    broadcast_id: int,
    audience: str = Form("all"),
    team: str = Form(""),
    participant: str = Form(""),
    message: str = Form(""),
    send_date: str = Form(...),
    send_time: str = Form(...),
    attachment: UploadFile | None = File(default=None),
    remove_attachment: bool = Form(default=False),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    team_id = int(team) if team else None
    participant_id = int(participant) if participant else None
    send_at = _to_utc(send_date, send_time)
    storage = S3Storage(get_settings())

    async with async_session_factory() as session:
        broadcast = await get_broadcast(session, broadcast_id)
        if broadcast is None or broadcast.sent_at is not None:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND)
        teams = await list_teams(session)
        participants = await list_all_applications(session)
        label = _audience_label(audience, team, participant, teams, participants)

        await update_broadcast(
            broadcast,
            message=message,
            audience_label=label,
            audience=audience,
            team_id=team_id,
            participant_id=participant_id,
            send_at=send_at,
        )

        photo_key, video_key = await _save_attachment(storage, broadcast.id, attachment)
        if photo_key or video_key:
            set_broadcast_attachment(broadcast, photo_key=photo_key, video_key=video_key)
        elif remove_attachment:
            set_broadcast_attachment(broadcast, photo_key=None, video_key=None)

        await session.commit()

    return RedirectResponse("/broadcast?edited=1", status_code=http_status.HTTP_303_SEE_OTHER)


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
