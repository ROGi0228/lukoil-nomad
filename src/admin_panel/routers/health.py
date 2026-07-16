from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from src.db.session import async_session_factory

router = APIRouter()


@router.get("/health", response_model=None)
async def health(request: Request, response: Response) -> dict[str, Any]:
    checks: dict[str, str] = {}
    healthy = True

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - healthcheck must never raise, just report
        checks["database"] = f"error: {exc}"
        healthy = False

    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"
        healthy = False

    response.status_code = 200 if healthy else 503
    return {"status": "ok" if healthy else "unhealthy", "checks": checks}
