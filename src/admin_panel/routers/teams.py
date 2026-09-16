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
from src.admin_panel.notify_helpers import notify_new_team_members
from src.bot.notify import notify_user
from src.core.config import get_settings
from src.db.models.admin_user import AdminUser
from src.db.models.task_dispatch import TaskDispatch
from src.db.repositories.application_repository import get_application, list_unassigned_applications
from src.db.repositories.task_repository import (
    list_dispatches_for_application,
    list_dispatches_for_team,
)
from src.db.repositories.team_repository import (
    add_point_adjustment,
    cancel_point_adjustment,
    create_team,
    get_point_adjustment,
    get_team,
    get_team_score,
    list_point_adjustments,
    list_team_member_contacts,
    list_teams,
    resolve_adjustment_contacts,
    update_point_adjustment,
)
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage

router = APIRouter(prefix="/teams")
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt

_ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _to_utc(date_str: str, time_str: str) -> dt.datetime:
    naive = dt.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=_ALMATY_TZ).astimezone(dt.UTC)


def _to_almaty_parts(value: dt.datetime) -> tuple[str, str]:
    local = value.astimezone(_ALMATY_TZ)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


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
    schedule_mode: str = Form(default="now"),
    send_date: str = Form(default=""),
    send_time: str = Form(default=""),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    """Ручная корректировка баллов — снять ошибочный штраф, начислить бонус и т.п.,
    независимо от конкретного задания. Баллы всегда идут на счёт команды — выбор
    получателя уведомления (вся команда, один участник или никто) на это не
    влияет. Можно начислить сразу или отложить на будущее (applied_at NULL, пока
    крон apply_scheduled_point_adjustments не заберёт по наступлении send_at) —
    баллы в счёт команды попадают только после фактического применения."""
    participant_id_int = int(participant_id) if participant_id else None

    if schedule_mode == "later" and send_date and send_time:
        send_at = _to_utc(send_date, send_time)
        applied_at = None
    else:
        send_at = dt.datetime.now(dt.UTC)
        applied_at = send_at

    async with async_session_factory() as session:
        adjustment = await add_point_adjustment(
            session,
            team_id=team_id,
            points=points,
            reason=reason,
            admin_user_id=admin.id,
            send_at=send_at,
            applied_at=applied_at,
            notify_scope=notify_scope,
            participant_id=participant_id_int,
        )
        await session.commit()
        contacts = await resolve_adjustment_contacts(session, adjustment) if applied_at else []

    # Причина уходит как есть, без добавленного координатором текста вроде
    # "Вашей команде начислены баллы: +N." — само число баллов, если нужно,
    # координатор пишет в тексте причины (см. плейсхолдер поля выше).
    if applied_at is not None:
        bot: Bot = request.app.state.bot
        for telegram_id, _language in contacts:
            await notify_user(bot, telegram_id, reason)

    return RedirectResponse(f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{team_id}/adjustments/{adjustment_id}/cancel", response_model=None)
async def cancel_point_adjustment_route(
    team_id: int,
    adjustment_id: int,
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    """Отменяет ещё не применённую запланированную корректировку — удаляет
    целиком, баллы за неё никогда не попадали в счёт команды (applied_at был
    NULL)."""
    async with async_session_factory() as session:
        adjustment = await get_point_adjustment(session, adjustment_id)
        if adjustment is None or adjustment.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if adjustment.applied_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        await cancel_point_adjustment(session, adjustment)
        await session.commit()

    return RedirectResponse(f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{team_id}/adjustments/{adjustment_id}/edit", response_class=HTMLResponse)
async def edit_point_adjustment_form(
    team_id: int,
    adjustment_id: int,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
) -> HTMLResponse:
    async with async_session_factory() as session:
        team = await get_team(session, team_id)
        adjustment = await get_point_adjustment(session, adjustment_id)
        if team is None or adjustment is None or adjustment.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    send_date, send_time = _to_almaty_parts(adjustment.send_at)

    return templates.TemplateResponse(
        request,
        "adjustment_edit.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "team": team,
            "adjustment": adjustment,
            "send_date": send_date,
            "send_time": send_time,
        },
    )


@router.post("/{team_id}/adjustments/{adjustment_id}/edit", response_model=None)
async def edit_point_adjustment_route(
    team_id: int,
    adjustment_id: int,
    request: Request,
    points: int = Form(...),
    reason: str = Form(...),
    notify: bool = Form(default=False),
    notify_scope: str = Form(default="team"),
    participant_id: str = Form(default=""),
    send_date: str = Form(default=""),
    send_time: str = Form(default=""),
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    participant_id_int = int(participant_id) if participant_id else None

    async with async_session_factory() as session:
        adjustment = await get_point_adjustment(session, adjustment_id)
        if adjustment is None or adjustment.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if adjustment.applied_at is None:
            # Ещё не применена — можно поправить и время/получателя, уведомление
            # (если оно вообще нужно) уйдёт кроном при фактическом применении,
            # а не сейчас.
            new_send_at = (
                _to_utc(send_date, send_time) if send_date and send_time else adjustment.send_at
            )
            await update_point_adjustment(
                adjustment,
                points=points,
                reason=reason,
                send_at=new_send_at,
                notify_scope=notify_scope,
                participant_id=participant_id_int,
            )
            await session.commit()
            return RedirectResponse(f"/teams/{team_id}", status_code=status.HTTP_303_SEE_OTHER)

        await update_point_adjustment(adjustment, points=points, reason=reason)
        await session.commit()

        contacts = await list_team_member_contacts(session, team_id) if notify else []

    if notify:
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
