import math

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette import status as http_status

from src.admin_panel.auth import get_current_admin
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from src.admin_panel.display import format_dt, parse_date
from src.db.models.admin_user import AdminUser
from src.db.repositories.app_settings_repository import (
    is_registration_closed,
    set_registration_closed,
)
from src.db.repositories.application_repository import count_applications, list_applications
from src.db.session import async_session_factory

router = APIRouter()
templates = Jinja2Templates(directory="src/admin_panel/templates")
templates.env.filters["format_dt"] = format_dt

PAGE_SIZE = 25


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    date_from_parsed = parse_date(date_from)
    date_to_parsed = parse_date(date_to)

    async with async_session_factory() as session:
        total_registered = await count_applications(session)
        registration_closed = await is_registration_closed(session)
        applications, total = await list_applications(
            session,
            date_from=date_from_parsed,
            date_to=date_to_parsed,
            search=search or None,
            page=page,
            page_size=PAGE_SIZE,
        )

    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "admin": admin,
            "csrf_token": get_csrf_token(request),
            "total_registered": total_registered,
            "applications": applications,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "registration_closed": registration_closed,
            "filters": {
                "date_from": date_from or "",
                "date_to": date_to or "",
                "search": search or "",
            },
        },
    )


@router.post("/registration/close", response_model=None)
async def close_registration(
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    async with async_session_factory() as session:
        await set_registration_closed(session, True)
        await session.commit()

    return RedirectResponse("/", status_code=http_status.HTTP_303_SEE_OTHER)


@router.post("/registration/open", response_model=None)
async def open_registration(
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(csrf_protect),
) -> RedirectResponse:
    async with async_session_factory() as session:
        await set_registration_closed(session, False)
        await session.commit()

    return RedirectResponse("/", status_code=http_status.HTTP_303_SEE_OTHER)
