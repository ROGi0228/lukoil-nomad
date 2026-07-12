import argparse
import asyncio

from src.admin_panel.auth import hash_password
from src.core.config import get_settings
from src.core.logging import configure_logging, get_logger
from src.db.models.admin_user import AdminUser
from src.db.session import async_session_factory

logger = get_logger(__name__)


async def create_admin_user(username: str, password: str) -> None:
    async with async_session_factory() as session:
        admin = AdminUser(username=username, password_hash=hash_password(password))
        session.add(admin)
        await session.commit()
    logger.info("admin_user_created", username=username)


def main() -> None:
    parser = argparse.ArgumentParser(description="Создать пользователя админ-панели")
    parser.add_argument("username")
    parser.add_argument("password")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)
    asyncio.run(create_admin_user(args.username, args.password))


if __name__ == "__main__":
    main()
