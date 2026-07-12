from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette import status

from src.admin_panel.auth import SESSION_KEY, verify_password
from src.db.models.admin_user import AdminUser
from src.db.session import async_session_factory

router = APIRouter()
templates = Jinja2Templates(directory="src/admin_panel/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_model=None)
async def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...)
) -> RedirectResponse | HTMLResponse:
    async with async_session_factory() as session:
        result = await session.execute(select(AdminUser).where(AdminUser.username == username))
        admin = result.scalar_one_or_none()

    if admin is None or not admin.is_active or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверный логин или пароль"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session[SESSION_KEY] = admin.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
