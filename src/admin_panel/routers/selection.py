from aiogram import Bot
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette import status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.bot.i18n import resolve_lang, t
from src.bot.notify import notify_user
from src.db.models.admin_user import AdminUser
from src.db.models.user import User
from src.db.repositories.application_repository import (
    list_stage1_candidates,
    list_stage2_candidates,
)
from src.db.session import async_session_factory
from src.shared.enums import SelectionStage

router = APIRouter(prefix="/selection")
templates = Jinja2Templates(directory="src/admin_panel/templates")


@router.get("", response_class=HTMLResponse)
async def selection_page(
    request: Request, admin: AdminUser = Depends(get_current_admin)
) -> HTMLResponse:
    async with async_session_factory() as session:
        stage1_candidates = await list_stage1_candidates(session)
        stage2_candidates = await list_stage2_candidates(session)

    return templates.TemplateResponse(
        request,
        "selection.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "stage1_candidates": stage1_candidates,
            "stage2_candidates": stage2_candidates,
        },
    )


@router.post("/stage1", response_model=None)
async def process_stage1(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
    selected_ids: list[int] = Form(default=[]),
) -> RedirectResponse:
    selected_set = set(selected_ids)
    notifications: list[tuple[int, str | None, SelectionStage]] = []

    async with async_session_factory() as session:
        candidates = await list_stage1_candidates(session)
        for application in candidates:
            new_stage = (
                SelectionStage.VOTING
                if application.id in selected_set
                else SelectionStage.ELIMINATED_STAGE1
            )
            application.selection_stage = new_stage
            user = await session.get(User, application.user_id)
            if user is not None:
                notifications.append((user.telegram_id, user.language, new_stage))
        await session.commit()

    bot: Bot = request.app.state.bot
    for telegram_id, language, new_stage in notifications:
        lang = resolve_lang(language)
        key = "advanced_to_voting" if new_stage == SelectionStage.VOTING else "eliminated_stage1"
        await notify_user(bot, telegram_id, t(lang, key))

    return RedirectResponse("/selection", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/stage2", response_model=None)
async def process_stage2(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
    selected_ids: list[int] = Form(default=[]),
) -> RedirectResponse:
    selected_set = set(selected_ids)
    notifications: list[tuple[int, str | None, SelectionStage]] = []

    async with async_session_factory() as session:
        candidates = await list_stage2_candidates(session)
        for application in candidates:
            new_stage = (
                SelectionStage.WINNER
                if application.id in selected_set
                else SelectionStage.ELIMINATED_STAGE2
            )
            application.selection_stage = new_stage
            user = await session.get(User, application.user_id)
            if user is not None:
                notifications.append((user.telegram_id, user.language, new_stage))
        await session.commit()

    bot: Bot = request.app.state.bot
    for telegram_id, language, new_stage in notifications:
        lang = resolve_lang(language)
        key = "winner_announcement" if new_stage == SelectionStage.WINNER else "eliminated_stage2"
        await notify_user(bot, telegram_id, t(lang, key))

    return RedirectResponse("/selection", status_code=status.HTTP_303_SEE_OTHER)
