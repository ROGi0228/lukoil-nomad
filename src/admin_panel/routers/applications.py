from aiogram import Bot
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.display import ACTION_LABELS, STATUS_LABELS, flag_label
from src.bot.fsm_control import set_fsm_state
from src.bot.notify import notify_user
from src.bot.states.document_states import DocumentStates
from src.bot.states.video_states import VideoStates
from src.core.config import get_settings
from src.db.models.admin_user import AdminUser
from src.db.models.application import Application
from src.db.models.user import User
from src.db.repositories.application_repository import get_application
from src.db.repositories.moderation_log_repository import create_log, list_logs_for_application
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage
from src.shared.enums import ApplicationStatus, ModerationAction

router = APIRouter(prefix="/applications")
templates = Jinja2Templates(directory="src/admin_panel/templates")


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
    settings = get_settings()
    storage = S3Storage(settings)

    async with async_session_factory() as session:
        application = await get_application(session, application_id)
        if application is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        logs = await list_logs_for_application(session, application_id)

    photo_url = (
        await storage.presigned_url(application.document_photo_key)
        if application.document_photo_key
        else None
    )
    video_url = (
        await storage.presigned_url(application.video_key) if application.video_key else None
    )

    ocr_raw_text = None
    ocr_parsed = None
    if application.ocr_raw_data:
        ocr_raw_text = application.ocr_raw_data.get("raw_text")
        ocr_parsed = application.ocr_raw_data.get("parsed")

    return templates.TemplateResponse(
        request,
        "application_detail.html",
        {
            "admin": admin,
            "application": application,
            "status_labels": STATUS_LABELS,
            "flag_label": flag_label,
            "photo_url": photo_url,
            "video_url": video_url,
            "ocr_raw_text": ocr_raw_text,
            "ocr_parsed": ocr_parsed,
            "logs": logs,
            "action_labels": ACTION_LABELS,
        },
    )


@router.post("/{application_id}/approve", response_model=None)
async def approve_application(
    application_id: int, request: Request, admin: AdminUser = Depends(get_current_admin)
) -> RedirectResponse:
    async with async_session_factory() as session:
        application, user = await _load_application_and_user(session, application_id)
        application.status = ApplicationStatus.APPROVED
        await create_log(
            session,
            application_id=application.id,
            admin_user_id=admin.id,
            action=ModerationAction.APPROVE,
        )
        await session.commit()
        telegram_id = user.telegram_id

    bot: Bot = request.app.state.bot
    await notify_user(
        bot,
        telegram_id,
        "Ваша заявка одобрена! Поздравляем — вы участник проекта Nomad Lukoil.",
    )
    return RedirectResponse(
        f"/applications/{application_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{application_id}/reject", response_model=None)
async def reject_application(
    application_id: int,
    request: Request,
    reason: str = Form(...),
    admin: AdminUser = Depends(get_current_admin),
) -> RedirectResponse:
    async with async_session_factory() as session:
        application, user = await _load_application_and_user(session, application_id)
        application.status = ApplicationStatus.REJECTED
        await create_log(
            session,
            application_id=application.id,
            admin_user_id=admin.id,
            action=ModerationAction.REJECT,
            reason=reason,
        )
        await session.commit()
        telegram_id = user.telegram_id

    bot: Bot = request.app.state.bot
    await notify_user(
        bot,
        telegram_id,
        f"К сожалению, ваша заявка отклонена. Причина: {reason}",
    )
    return RedirectResponse(
        f"/applications/{application_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{application_id}/request-photo", response_model=None)
async def request_photo_again(
    application_id: int, request: Request, admin: AdminUser = Depends(get_current_admin)
) -> RedirectResponse:
    settings = get_settings()
    async with async_session_factory() as session:
        application, user = await _load_application_and_user(session, application_id)
        application.document_photo_key = None
        application.document_number = None
        application.document_iin = None
        application.document_expiry_date = None
        application.status = ApplicationStatus.PENDING_DOCUMENT
        await create_log(
            session,
            application_id=application.id,
            admin_user_id=admin.id,
            action=ModerationAction.REQUEST_REUPLOAD_PHOTO,
        )
        await session.commit()
        telegram_id = user.telegram_id

    bot: Bot = request.app.state.bot
    await set_fsm_state(bot, settings.redis_url, telegram_id, DocumentStates.waiting_photo)
    await notify_user(
        bot,
        telegram_id,
        "Модератор попросил прислать фото водительского удостоверения ещё раз. "
        "Пришлите, пожалуйста, новое фото.",
    )
    return RedirectResponse(
        f"/applications/{application_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{application_id}/request-video", response_model=None)
async def request_video_again(
    application_id: int, request: Request, admin: AdminUser = Depends(get_current_admin)
) -> RedirectResponse:
    settings = get_settings()
    async with async_session_factory() as session:
        application, user = await _load_application_and_user(session, application_id)
        application.video_key = None
        application.status = ApplicationStatus.PENDING_VIDEO
        await create_log(
            session,
            application_id=application.id,
            admin_user_id=admin.id,
            action=ModerationAction.REQUEST_REUPLOAD_VIDEO,
        )
        await session.commit()
        telegram_id = user.telegram_id

    bot: Bot = request.app.state.bot
    await set_fsm_state(bot, settings.redis_url, telegram_id, VideoStates.waiting_video)
    await notify_user(
        bot,
        telegram_id,
        "Модератор попросил прислать видео-визитку ещё раз. Пришлите, пожалуйста, новое видео.",
    )
    return RedirectResponse(
        f"/applications/{application_id}", status_code=status.HTTP_303_SEE_OTHER
    )
