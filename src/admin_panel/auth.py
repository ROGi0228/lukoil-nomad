from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from starlette.requests import Request

from src.db.models.admin_user import AdminUser
from src.db.session import async_session_factory

SESSION_KEY = "admin_user_id"

_hasher = PasswordHasher()


class NotAuthenticatedError(Exception):
    """Поднимается зависимостью get_current_admin, перехватывается exception_handler'ом
    в main.py и превращается в редирект на /login — так чище, чем возвращать Response
    напрямую из FastAPI-зависимости."""


def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw_password)
    except VerifyMismatchError:
        return False


async def get_current_admin(request: Request) -> AdminUser:
    admin_id = request.session.get(SESSION_KEY)
    if admin_id is None:
        raise NotAuthenticatedError()

    async with async_session_factory() as session:
        admin = await session.get(AdminUser, admin_id)

    if admin is None or not admin.is_active:
        raise NotAuthenticatedError()

    return admin
