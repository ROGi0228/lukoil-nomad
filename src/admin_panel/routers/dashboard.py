from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.admin_panel.auth import get_current_admin
from src.db.models.admin_user import AdminUser

router = APIRouter()
templates = Jinja2Templates(directory="src/admin_panel/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request, admin: AdminUser = Depends(get_current_admin)
) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html", {"admin": admin})
