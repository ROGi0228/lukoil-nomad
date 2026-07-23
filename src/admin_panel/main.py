from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from starlette import status
from starlette.middleware.sessions import SessionMiddleware

from src.admin_panel.auth import NotAuthenticatedError
from src.admin_panel.routers import applications, auth, dashboard, health, selection
from src.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    redis: Redis = Redis.from_url(settings.redis_url)
    app.state.bot = bot
    app.state.redis = redis
    try:
        yield
    finally:
        await redis.aclose()
        await bot.session.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Nomad Lukoil — админ-панель", lifespan=lifespan)

    app.add_middleware(SessionMiddleware, secret_key=settings.admin_panel_secret_key)
    app.mount("/static", StaticFiles(directory="src/admin_panel/static"), name="static")

    @app.exception_handler(NotAuthenticatedError)
    async def not_authenticated_handler(
        _request: Request, _exc: NotAuthenticatedError
    ) -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(applications.router)
    app.include_router(selection.router)

    return app


app = create_app()
