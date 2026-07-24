import asyncio
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from arq.connections import RedisSettings
from arq.cron import cron

from src.core.config import get_settings
from src.core.logging import configure_logging, get_logger
from src.workers.tasks.ocr_tasks import process_document_ocr
from src.workers.tasks.task_scheduler import (
    apply_deadline_penalties,
    dispatch_due_tasks,
    dispatch_trigger_based_tasks,
)

logger = get_logger(__name__)

# arq синхронно вызывает asyncio.get_event_loop() при создании Worker, ещё до
# запуска цикла событий. Под uvloop (транзитивная зависимость arq на Linux)
# такой вызов падает с "There is no current event loop", если loop заранее не
# установлен явно — устанавливаем здесь, до того как arq успеет создать Worker.
asyncio.set_event_loop(asyncio.new_event_loop())


async def startup(ctx: dict[str, Any]) -> None:
    ctx["bot"] = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    logger.info("worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    bot: Bot | None = ctx.get("bot")
    if bot is not None:
        await bot.session.close()
    logger.info("worker_stopped")


# arq отказывается стартовать без ни одной зарегистрированной задачи —
# заглушка остаётся полезной как лёгкий healthcheck-джоб
async def health_check(ctx: dict[str, Any]) -> str:
    return "ok"


settings = get_settings()
configure_logging(settings)


class WorkerSettings:
    functions: list[Any] = [health_check, process_document_ocr]
    # Раз в минуту: разослать задания, у которых наступило время отправки, отправить
    # задания-триггеры командам, выполнившим предыдущее задание, и оштрафовать команды,
    # просрочившие дедлайн по уже отправленным заданиям.
    cron_jobs: list[Any] = [
        cron(dispatch_due_tasks),
        cron(dispatch_trigger_based_tasks),
        cron(apply_deadline_penalties),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
