import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from redis.asyncio import Redis

from src.bot.handlers import admin, registration, rules, start, tasks, team_info
from src.bot.middlewares.db_session import DbSessionMiddleware
from src.bot.middlewares.logging import LoggingMiddleware
from src.bot.middlewares.throttling import ThrottlingMiddleware
from src.core.config import Settings, get_settings
from src.core.logging import configure_logging, get_logger
from src.db.session import async_session_factory
from src.services.storage.s3_storage import S3Storage

logger = get_logger(__name__)

WEBHOOK_PATH = "/webhook"
WEBHOOK_SERVER_PORT = 8080


def create_dispatcher(settings: Settings, redis: Redis, storage: S3Storage) -> Dispatcher:
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis))
    dispatcher["settings"] = settings
    dispatcher["storage"] = storage

    dispatcher.update.middleware(LoggingMiddleware())
    dispatcher.update.middleware(ThrottlingMiddleware(redis=redis))
    dispatcher.update.middleware(DbSessionMiddleware(session_factory=async_session_factory))

    dispatcher.include_router(start.router)
    dispatcher.include_router(registration.router)
    dispatcher.include_router(rules.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(tasks.router)
    dispatcher.include_router(team_info.router)
    return dispatcher


_USER_COMMANDS = {
    "ru": [
        BotCommand(command="start", description="О проекте / регистрация"),
        BotCommand(command="tasks", description="Задания моей команды"),
        BotCommand(command="points", description="Баллы моей команды"),
        BotCommand(command="leaderboard", description="Рейтинг команд"),
        BotCommand(command="rules", description="Правила для участников"),
        BotCommand(command="language", description="Сменить язык"),
    ],
    "kk": [
        BotCommand(command="start", description="Жоба туралы / тіркелу"),
        BotCommand(command="tasks", description="Командамның тапсырмалары"),
        BotCommand(command="points", description="Командамның ұпайлары"),
        BotCommand(command="leaderboard", description="Командалар рейтингі"),
        BotCommand(command="rules", description="Қатысушыларға арналған ережелер"),
        BotCommand(command="language", description="Тілді өзгерту"),
    ],
}


async def _setup_bot_commands(bot: Bot, settings: Settings) -> None:
    for lang_code, commands in _USER_COMMANDS.items():
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault(), language_code=lang_code)
    await bot.set_my_commands(_USER_COMMANDS["ru"], scope=BotCommandScopeDefault())

    admin_commands = [
        *_USER_COMMANDS["ru"],
        BotCommand(command="admin", description="Панель администратора"),
    ]
    for admin_id in settings.admin_telegram_ids:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            logger.exception("set_admin_commands_failed", admin_id=admin_id)


async def _run_polling(bot: Bot, dispatcher: Dispatcher) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


async def _run_webhook(bot: Bot, dispatcher: Dispatcher, settings: Settings) -> None:
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret or None,
        drop_pending_updates=True,
    )

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.webhook_secret or None,
    ).register(app, path=WEBHOOK_PATH)
    setup_application(app, dispatcher, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=WEBHOOK_SERVER_PORT)
    await site.start()

    logger.info("webhook_listening", path=WEBHOOK_PATH, port=WEBHOOK_SERVER_PORT)
    await asyncio.Event().wait()


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    redis: Redis = Redis.from_url(settings.redis_url)
    storage = S3Storage(settings)
    await storage.ensure_bucket_exists()
    dispatcher = create_dispatcher(settings, redis, storage)

    await _setup_bot_commands(bot, settings)

    me = await bot.get_me()
    logger.info(
        "bot_started",
        username=me.username,
        environment=settings.environment,
        mode="webhook" if settings.bot_use_webhook else "polling",
    )

    try:
        if settings.bot_use_webhook:
            await _run_webhook(bot, dispatcher, settings)
        else:
            await _run_polling(bot, dispatcher)
    finally:
        await redis.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
