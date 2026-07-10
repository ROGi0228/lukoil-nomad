from arq.connections import RedisSettings

from src.core.config import get_settings
from src.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    logger.info("worker_started")


async def shutdown(ctx: dict) -> None:
    logger.info("worker_stopped")


# arq отказывается стартовать без ни одной зарегистрированной задачи —
# заглушка до реальных задач (OCR/видео/уведомления) в Фазе 3+.
async def health_check(ctx: dict) -> str:
    return "ok"


settings = get_settings()
configure_logging(settings)


class WorkerSettings:
    functions: list = [health_check]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
