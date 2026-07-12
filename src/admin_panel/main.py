from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette import status
from starlette.middleware.sessions import SessionMiddleware

from src.admin_panel.auth import NotAuthenticatedError
from src.admin_panel.routers import auth, dashboard
from src.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Nomad Lukoil — админ-панель")

    app.add_middleware(SessionMiddleware, secret_key=settings.admin_panel_secret_key)
    app.mount("/static", StaticFiles(directory="src/admin_panel/static"), name="static")

    @app.exception_handler(NotAuthenticatedError)
    async def not_authenticated_handler(
        _request: Request, _exc: NotAuthenticatedError
    ) -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    app.include_router(auth.router)
    app.include_router(dashboard.router)

    return app


app = create_app()
